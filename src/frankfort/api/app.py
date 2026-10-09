"""La capa HTTP sobre el motor de medición.

Un endpoint que importa —`POST /audit`— y uno de salud. Nada más, y a
propósito: el motor es determinista y sin estado, así que la API es una
función pura vestida de HTTP. Ni sesiones, ni base de datos, ni
autenticación todavía; el grafo de agentes y su checkpointer son el
siguiente paso y vivirán por encima de esto, no dentro.

── Lo que NO hace ───────────────────────────────────────────────
No recibe fotografías. Recibe COORDENADAS, que es lo que el motor
necesita, y es también la decisión de privacidad de la arquitectura
(§«privacidad real»): el landmarking ocurre en el navegador y las caras
no salen de ahí para medir. Lo único que cruza la red son parejas de
números y el sello de calidad de la captura.

── Por qué el marcado viaja entero en cada petición ─────────────
Porque medir es barato y sin estado: un `POST /audit` completo cuesta
unas décimas de segundo y se puede repetir cuando al usuario le
apetezca. Guardar el marcado en el servidor para "ahorrar" obligaría a
tener sesión, expiración y borrado de datos de alguien — mucha
superficie a cambio de nada.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..agents import explain, personalize, provider_from_env
from ..insight import build_insights
from ..observer import observe, vision_from_env
from ..narrative import Measured
from ..recommender import ObservationIn, build_plan, write_intro
from ..auditor import AuditReport, audit_view, cross_check_profiles
from ..narrative import build_brief
from ..landmarks import Point, View
from ..metrics import REGISTRY
from ..reliability import (
    MarkedPoint,
    MarkingSet,
    MissingScalePoints,
    reference_scale,
)
from .schemas import (
    AuditRequest,
    AuditResponse,
    CrossCheckOut,
    Health,
    InsightOut,
    ObservationOut,
    ObserveRequest,
    ObserveResponse,
    OptionWire,
    CostOut,
    PlanRequest,
    PlanResponse,
    StepOut,
    VetoedOut,
    MetricOut,
    ViewMarking,
)

#: Orígenes permitidos. En desarrollo, el Next local. En producción se
#: pasa por entorno — una lista abierta en una API que recibe
#: coordenadas de la cara de alguien no es aceptable ni siendo anónimas.
DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def cors_origins() -> list[str]:
    raw = os.getenv("FRANKFORT_CORS_ORIGINS", DEFAULT_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(
    title="Frankfort",
    version=__version__,
    summary="Métricas faciales con auditoría de la propia medición",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok", version=__version__, metrics=len(REGISTRY))


def _marking_set(payload: ViewMarking) -> MarkingSet:
    """Del cable al dominio, con los errores traducidos a 422.

    Las tres cosas que pueden ir mal aquí —pareja de escala ausente,
    escala degenerada y número de pasadas inválido— son culpa de la
    petición, no del servidor, y merecen un mensaje que diga qué punto
    falla. Un 500 genérico dejaría al cliente adivinando.
    """
    points = {
        point: MarkedPoint(point=point, passes=tuple(tuple(c) for c in passes))
        for point, passes in payload.points.items()
    }

    try:
        scale = reference_scale(payload.view, points)
    except MissingScalePoints as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{payload.view.value}: {exc}. Sin ella no hay contra qué "
                f"comparar las discrepancias del doble marcado."
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{payload.view.value}: {exc}") from exc

    return MarkingSet(
        points=points,
        scale=scale,
        capture_grade=payload.capture_grade,
    )


@app.post("/audit", response_model=AuditResponse)
def audit(request: AuditRequest) -> AuditResponse:
    """Audita el marcado de una o varias vistas.

    Una pasada por vista y, si vienen los dos perfiles, el control
    cruzado entre ellos. El resultado es reproducible: misma entrada,
    mismo informe, incluidas las bandas de error —el muestreo de
    `propagate_error` va con semilla fija.
    """
    reports: dict[View, AuditReport] = {}
    metrics: list[MetricOut] = []
    unreliable: set[Point] = set()
    missing_double: set[Point] = set()

    for payload in request.views:
        marking = _marking_set(payload)
        report = audit_view(marking, payload.view)
        reports[payload.view] = report

        metrics.extend(MetricOut.of(m, payload.view) for m in report.metrics)
        unreliable.update(report.unreliable_points)
        missing_double.update(report.missing_double_marks)

    right = reports.get(View.PROFILE_RIGHT)
    left = reports.get(View.PROFILE_LEFT)
    crosses = (
        cross_check_profiles(right, left)
        if right is not None and left is not None
        else []
    )

    #: El sello del conjunto es el PEOR de sus fotografías, igual que en
    #: el cliente (`overallGrade`): un informe no puede presumir de la
    #: mejor toma cuando una de las medidas sale de la peor.
    grade = max(
        (v.capture_grade for v in request.views), key="ABC".index, default=None
    )
    brief = build_brief(
        {v.value: r for v, r in reports.items()},
        crosses,
        locale=request.locale,
        grade=grade,
    )
    provider = provider_from_env()
    explanation = explain(brief, provider)
    if explanation.rejected:
        #: A la consola del servidor, no al cliente: es información para
        #: arreglar el prompt o el proveedor, no para quien lee su cara.
        print(f"[frankfort] resumen del agente descartado: {explanation.rejected}")

    personalized = personalize(
        build_insights(brief, {c.metric: c.verdict for c in crosses}),
        brief,
        provider,
    )
    for where, why in personalized.rejected.items():
        print(f"[frankfort] explicación descartada ({where}): {why}")

    return AuditResponse(
        metrics=metrics,
        cross_checks=[CrossCheckOut.of(c) for c in crosses],
        unreliable_points=sorted(unreliable, key=lambda p: p.value),
        missing_double_marks=sorted(missing_double, key=lambda p: p.value),
        summary=explanation.text,
        summary_source=explanation.source,
        insights=[
            InsightOut(
                name=i.name,
                what=i.what,
                reading=i.reading,
                meaning=i.meaning,
                position=i.position,
                certainty=i.certainty,
                options=[OptionWire(level=o.level, text=o.text) for o in i.options],
                no_options=i.no_options,
                source=i.source,
            )
            for i in personalized.insights
        ],
    )


@app.post("/observe", response_model=ObserveResponse)
def observe_photos(request: ObserveRequest) -> ObserveResponse:
    """Lo que un modelo de visión ve en las fotos: piel, sonrisa, volumen.

    Las fotos se usan para esta llamada y se descartan: ni disco, ni log,
    ni caché. Sin proveedor de visión configurado responde con
    observaciones de EJEMPLO, y lo dice en `source`.
    """
    import base64
    import binascii

    photos: dict[str, bytes] = {}
    for view, data in request.photos.items():
        try:
            photos[view.value] = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail=f"{view.value}: base64 inválido"
            ) from exc

    report = observe(photos, request.locale, vision_from_env())
    for why in report.rejected:
        print(f"[frankfort] observación descartada: {why}")

    return ObserveResponse(
        observations=[
            ObservationOut(
                tag=o.tag,
                area=o.area,
                view=View(o.view),
                claim=o.claim,
                evidence=o.evidence,
                confidence=o.confidence,
                corroborating_views=[View(v) for v in o.corroborating_views],
            )
            for o in report.observations
        ],
        source=report.source,
        model=report.model,
    )


@app.post("/plan", response_model=PlanResponse)
def plan(request: PlanRequest) -> PlanResponse:
    """El plan de pasos: de lo gratis a lo médico, con precios del país.

    Recibe las medidas tal como las devolvió `/audit` y las observaciones
    de `/observe`, y recalcula todo lo que decide algo —posición respecto
    al rango, certeza, nivel permitido— a partir de las cifras. Las reglas
    viven en `recommender.py`; el LLM, si lo hay, solo redacta la
    introducción.
    """
    measured = []
    for m in request.metrics:
        low, high = m.reference
        inside = low <= m.value <= high
        width = (high - low) or 1.0
        off = 0.0 if inside else (
            (m.value - high) / width if m.value > high else (low - m.value) / width
        )
        measured.append(
            Measured(
                name=m.name, value=m.value, unit=m.unit, band=m.error_band,
                low=low, high=high, inside=inside,
                side="none" if inside else ("low" if m.value < low else "high"),
                off=off,
            )
        )
    observations = [
        ObservationIn(o.tag, o.confidence, corroborated=len(o.corroborating_views) > 0)
        for o in request.observations
    ]
    result = build_plan(
        measured, observations, country=request.country, locale=request.locale
    )
    result = write_intro(result, request.locale, provider_from_env())

    return PlanResponse(
        intro=result.intro,
        intro_source=result.intro_source,
        currency=result.currency,
        steps=[
            StepOut(
                level=s.level, text=s.text, reason=s.reason, source=s.source,
                cost=CostOut(low=s.cost[0], high=s.cost[1]) if s.cost else None,
                deferred=s.deferred,
            )
            for s in result.steps
        ],
        vetoed=[VetoedOut(text=v.text, reason=v.reason, why=v.why) for v in result.vetoed],
    )

"""El formato de cable de la API: lo que entra y lo que sale.

── Por qué hay esquemas y no se serializan las dataclasses ──────
Las dataclasses del motor son el dominio; estos modelos son el
contrato con el cliente. Separarlos permite que el motor cambie un
campo interno sin romper a nadie, y permite que el cable use
`camelCase` mientras el Python sigue en `snake_case`. Un mapeo en un
único sitio en vez de conversiones repartidas por el cliente.

── camelCase a propósito ────────────────────────────────────────
El consumidor es el frontend, y su espejo del contrato
(`web/src/lib/report/types.ts`) ya está en camelCase, que es la
convención de TypeScript. Podría hacer la conversión él, pero entonces
habría que mantener la tabla de nombres en el lado que NO define el
formato. La define quien lo emite.

── Coordenadas en píxeles ───────────────────────────────────────
El cliente guarda sus marcas normalizadas (0..1) para que sobrevivan al
zoom, y multiplica por el tamaño de la imagen antes de enviarlas. El
motor mide en píxeles y aquí no se normaliza nada: una coordenada del
cable significa exactamente lo que un CV normal entiende por
coordenada, y `width`/`height` sirven para validar que cae dentro.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from ..agents import Source
from ..auditor import CrossCheck, MetricResult, Status, SuppressionReason
from ..landmarks import Point, View
from ..narrative import Locale
from ..reliability import CaptureGrade


class Wire(BaseModel):
    """Base de todo lo que viaja: camelCase fuera, snake_case dentro."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


Coord = Annotated[list[float], Field(min_length=2, max_length=2)]

#: Una o dos pasadas. Tres no existe en el contrato del motor:
#: `MarkedPoint` lanza con más de dos, y el límite se aplica aquí para
#: que el error sea un 422 con su campo y no una excepción a mitad del
#: cálculo.
Passes = Annotated[list[Coord], Field(min_length=1, max_length=2)]


class ViewMarking(Wire):
    """El marcado de UNA fotografía."""

    view: View
    #: Sale de la validación de captura en el navegador y ensancha la
    #: banda de error (`GRADE_FACTOR`). Por defecto "A" para que un
    #: cliente que no valide no obtenga bandas artificialmente anchas
    #: sin saberlo.
    capture_grade: CaptureGrade = "A"
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    points: dict[Point, Passes] = Field(min_length=1)

    @model_validator(mode="after")
    def _inside_the_frame(self) -> ViewMarking:
        """Ninguna marca puede caer fuera de su fotografía.

        No es quisquillosidad: una coordenada fuera del encuadre suele
        significar que el cliente normalizó mal o mezcló dos imágenes, y
        el motor lo aceptaría sin rechistar produciendo una medida
        plausible y falsa.
        """
        for point, passes in self.points.items():
            for i, (x, y) in enumerate(passes):
                if not (0 <= x <= self.width and 0 <= y <= self.height):
                    raise ValueError(
                        f"{point.value}: la marca {i + 1} cae fuera de la "
                        f"imagen ({x}, {y}) en {self.width}×{self.height}"
                    )
        return self


class AuditRequest(Wire):
    views: list[ViewMarking] = Field(min_length=1)
    #: En qué idioma se redacta el resumen. El resto de la respuesta son
    #: números y claves, que no se traducen: los textos de la interfaz
    #: los pone el diccionario del cliente. Lo único que el servidor
    #: escribe en prosa es el resumen, y por eso es lo único que necesita
    #: saber el idioma.
    locale: Locale = "es"

    @model_validator(mode="after")
    def _no_repeated_views(self) -> AuditRequest:
        seen = [v.view for v in self.views]
        dupes = {v for v in seen if seen.count(v) > 1}
        if dupes:
            names = ", ".join(sorted(v.value for v in dupes))
            raise ValueError(f"vistas repetidas: {names}")
        return self


class MetricOut(Wire):
    name: str
    unit: str
    status: Status
    value: float | None
    error_band: float | None
    deviation: float
    reference: tuple[float, float] | None
    depends_on: list[Point]
    reason: SuppressionReason | None
    #: De qué fotografía salió. No está en `MetricResult` —el motor
    #: audita una vista cada vez— y lo añade la API al juntarlas, porque
    #: el informe enseña la misma métrica medida en los dos perfiles y
    #: tiene que poder decir cuál es cuál.
    view: View

    @classmethod
    def of(cls, result: MetricResult, view: View) -> MetricOut:
        return cls(
            name=result.name,
            unit=result.unit,
            status=result.status,
            value=result.value,
            error_band=result.error_band,
            deviation=result.deviation,
            reference=result.reference,
            depends_on=list(result.depends_on),
            reason=result.reason,
            view=view,
        )


class OptionWire(Wire):
    #: 0 gratis/hábito · 1 cosmético · 2 médico sin cirugía · 3 cirugía.
    level: int
    text: str


class InsightOut(Wire):
    """La explicación personalizada de UNA medida.

    `reading` y `meaning` los redacta el agente cuando hay proveedor (y
    `source` lo dice); `what` y `options` salen siempre de la base de
    conocimiento, filtradas por una regla de proporcionalidad que el
    modelo no controla. Ver `insight.py` y `agents.personalize`.
    """

    name: str
    what: str
    reading: str
    meaning: str
    position: str
    certainty: str
    options: list[OptionWire]
    no_options: str | None
    source: str


class CrossCheckOut(Wire):
    metric: str
    right: float
    left: float
    difference: float
    combined_band: float
    verdict: str

    @classmethod
    def of(cls, check: CrossCheck) -> CrossCheckOut:
        return cls(
            metric=check.metric,
            right=check.right,
            left=check.left,
            difference=check.difference,
            combined_band=check.combined_band,
            verdict=check.verdict,
        )


class AuditResponse(Wire):
    """Lo que el MOTOR sabe. Ni una cosa más.

    El sello de captura, las vistas que faltan y las métricas que ese
    sello deja fuera no viajan de vuelta aunque el cliente los haya
    enviado: los produce el navegador y los tiene delante. Devolvérselos
    solo crearía una segunda copia que podría contradecir a la primera.
    """

    metrics: list[MetricOut]
    cross_checks: list[CrossCheckOut]
    unreliable_points: list[Point]
    missing_double_marks: list[Point]
    #: El resumen en lenguaje llano. Lo redacta el servidor —con agente
    #: si hay proveedor, con plantillas si no— porque es lo único del
    #: informe que exige sintetizar varias medidas a la vez, y eso no es
    #: trabajo de la capa de presentación.
    summary: str = ""
    #: `agent` o `engine`. Va al cliente a propósito: un informe que no
    #: puede decir de dónde sale su propio texto es justo el producto que
    #: esta web dice no ser.
    summary_source: Source = "engine"
    #: Una explicación por medida publicable. Las suprimidas no tienen:
    #: no hay nada que explicarle a nadie de un número que no se publica.
    insights: list[InsightOut] = Field(default_factory=list)


class Health(Wire):
    status: str
    version: str
    #: Cuántas métricas sabe calcular este motor. Es el dato que delata
    #: un despliegue viejo mejor que el número de versión.
    metrics: int


# ───────────────────────── observador visual ─────────────────────────

#: ~4,5 MB de JPEG por foto en base64. El cliente las reduce a 1024 px
#: antes de mandarlas; esto es el tope para que nadie suba un RAW.
MAX_PHOTO_B64 = 6_000_000


class ObserveRequest(Wire):
    """Las fotos que el usuario ACEPTÓ mandar al observador visual.

    Es la única petición de la API que lleva imágenes: medir no las
    necesita (viajan coordenadas), describir sí. Por eso `consent` es
    obligatorio y tiene que ser `true` — no un valor por defecto, sino un
    sí explícito que el cliente solo manda después de que la persona
    pulse el botón que lo explica.
    """

    locale: Locale = "es"
    consent: bool
    photos: dict[View, str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _consented_and_bounded(self) -> ObserveRequest:
        if self.consent is not True:
            raise ValueError("sin consentimiento explícito no se analiza ninguna foto")
        for view, data in self.photos.items():
            if len(data) > MAX_PHOTO_B64:
                raise ValueError(f"{view.value}: foto demasiado grande")
        return self


class ObservationOut(Wire):
    tag: str
    area: str
    view: View
    claim: str
    evidence: str
    confidence: str
    corroborating_views: list[View]


class ObserveResponse(Wire):
    observations: list[ObservationOut]
    #: `agent` = lo vio un modelo; `example` = observaciones de ejemplo,
    #: porque no hay proveedor de visión configurado. El cliente lo enseña.
    source: str
    model: str | None


# ───────────────────────────── el plan ─────────────────────────────


class PlanMetricIn(Wire):
    """Una medida tal como la devolvió `/audit`. El servidor recalcula a
    partir de estas cifras la posición, la certeza y el nivel permitido:
    no se fía de que el cliente se los diga."""

    name: str
    unit: str
    value: float
    error_band: float = Field(ge=0)
    reference: tuple[float, float]


class PlanObservationIn(Wire):
    tag: str
    confidence: Literal["clear", "probable", "uncertain"]
    corroborating_views: list[View] = Field(default_factory=list)


class PlanRequest(Wire):
    locale: Locale = "es"
    country: Literal["ES", "MX", "CO", "AR", "US"] = "ES"
    metrics: list[PlanMetricIn] = Field(default_factory=list)
    observations: list[PlanObservationIn] = Field(default_factory=list)


class CostOut(Wire):
    low: int
    high: int


class StepOut(Wire):
    level: int
    text: str
    reason: str
    source: str
    cost: CostOut | None
    deferred: str | None


class VetoedOut(Wire):
    text: str
    reason: str
    why: str


class PlanResponse(Wire):
    intro: str
    intro_source: str
    currency: str
    steps: list[StepOut]
    #: Lo que el revisor de seguridad retiró, con el motivo. Se devuelve
    #: siempre: un revisor que retira en silencio no se distingue de uno
    #: que no hace nada.
    vetoed: list[VetoedOut]

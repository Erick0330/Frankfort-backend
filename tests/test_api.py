"""La capa HTTP, de punta a punta.

Estos tests no vuelven a comprobar la aritmética del motor —para eso
están test_metrics, test_reliability y test_auditor— sino lo que la API
añade encima: el formato de cable, la validación de la petición, la
escala calculada a partir de los propios puntos, y que el informe que
sale por el socket siga diciendo lo mismo que dice el motor.

Las coordenadas son las de `conftest.py`, desplazadas para que ninguna
caiga en negativo: la API rechaza marcas fuera del encuadre, y una
fixture con y=−0,5 estaría probando el validador en vez de la métrica.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frankfort import __version__
from frankfort.api import app
from frankfort.metrics import REGISTRY

client = TestClient(app)

#: Plano de Frankfort horizontal de 60 px: la escala de las vistas de
#: perfil, y el denominador de todas las discrepancias.
FRANKFORT = {"porion": [[10.0, 45.0]], "orbitale": [[70.0, 45.0]]}

#: Tercios exactos: 10 → 40 → 70 → 100, treinta píxeles cada uno.
#: Doble marcado con 1 px de discrepancia = 1,7 % de la escala, muy por
#: debajo de la tolerancia del 6 %.
THIRDS_CLEAN = {
    "trichion": [[50.0, 9.5], [50.0, 10.5]],
    "glabella": [[50.0, 39.5], [50.0, 40.5]],
    "subnasale": [[50.0, 69.5], [50.0, 70.5]],
    "menton": [[50.0, 99.5], [50.0, 100.5]],
}

#: Igual, pero Subnasale marcado con 6 px de diferencia: 10 % de la
#: escala, por encima de la tolerancia. Es el caso de la portada.
THIRDS_DIRTY = {
    **THIRDS_CLEAN,
    "subnasale": [[50.0, 67.0], [50.0, 73.0]],
}


def view(name: str, points: dict, grade: str = "A") -> dict:
    return {
        "view": name,
        "captureGrade": grade,
        "width": 200,
        "height": 200,
        "points": points,
    }


def audit(*views: dict) -> dict:
    response = client.post("/audit", json={"views": list(views)})
    assert response.status_code == 200, response.text
    return response.json()


def by_name(payload: dict, name: str) -> list[dict]:
    return [m for m in payload["metrics"] if m["name"] == name]


# ─────────────────────────── salud ───────────────────────────


def test_health_dice_la_version_y_cuantas_metricas_sabe():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["metrics"] == len(REGISTRY)


def test_la_version_del_paquete_es_la_del_pyproject():
    """Una API que anuncia otra versión hace imposible saber qué hay
    desplegado, que es justo para lo que se mira `/health`."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text("utf-8"))["project"]["version"]
    assert __version__ == declared


# ──────────────────────── el caso de la portada ────────────────────────


def test_tercios_limpios_se_reportan_los_tres():
    body = audit(view("profile_right", {**FRANKFORT, **THIRDS_CLEAN}))

    for name in ("upper_third_pct", "middle_third_pct", "lower_third_pct"):
        (metric,) = by_name(body, name)
        assert metric["status"] == "reported", metric
        assert metric["value"] == pytest.approx(33.333, abs=0.01)
        assert metric["errorBand"] is not None
        assert metric["view"] == "profile_right"

    assert body["unreliablePoints"] == []


def test_subnasale_sucio_tumba_dos_tercios_y_deja_el_superior():
    """El caso completo de la sección «Lo que descartamos», por HTTP.

    Un punto frágil cuyas dos marcas discrepan un 10 % arrastra todo lo
    que depende de él. El tercio superior va de Trichion a Glabella, no
    lo toca, y sobrevive: uno de tres.
    """
    body = audit(view("profile_right", {**FRANKFORT, **THIRDS_DIRTY}))

    assert body["unreliablePoints"] == ["subnasale"]

    (upper,) = by_name(body, "upper_third_pct")
    assert upper["status"] == "reported"

    for name in ("middle_third_pct", "lower_third_pct"):
        (metric,) = by_name(body, name)
        assert metric["status"] == "suppressed", metric
        assert metric["reason"] == "unreliable_dependency"
        assert metric["value"] is None
        assert "subnasale" in metric["dependsOn"]


def test_toda_metrica_que_dependa_del_punto_sucio_cae():
    """La cascada, en las dos direcciones: no se escapa ninguna."""
    body = audit(view("profile_right", {**FRANKFORT, **THIRDS_DIRTY}))
    sucios = set(body["unreliablePoints"])

    for metric in body["metrics"]:
        if sucios & set(metric["dependsOn"]):
            assert metric["status"] == "suppressed", metric["name"]
            assert metric["reason"] == "unreliable_dependency"


# ──────────────────────── formato de cable ────────────────────────


def test_el_cable_va_en_camelcase():
    """El consumidor es TypeScript y su espejo del contrato ya está en
    camelCase. Lo convierte quien emite el formato, no quien lo lee."""
    body = audit(view("profile_right", {**FRANKFORT, **THIRDS_CLEAN}))

    assert set(body) == {
        "metrics",
        "crossChecks",
        "unreliablePoints",
        "missingDoubleMarks",
        "summary",
        "summarySource",
        "insights",
    }
    metric = body["metrics"][0]
    assert "errorBand" in metric and "error_band" not in metric
    assert "dependsOn" in metric and "depends_on" not in metric


def test_la_respuesta_no_devuelve_lo_que_el_navegador_ya_sabe():
    """El sello de captura viene en la petición y NO vuelve. Devolverlo
    crearía una segunda copia del mismo dato que podría contradecir a la
    del cliente."""
    body = audit(view("profile_right", {**FRANKFORT, **THIRDS_CLEAN}, grade="C"))
    assert "grade" not in body
    assert "captureGrade" not in body


def test_mismo_marcado_mismo_informe():
    """Reproducible al bit, bandas de error incluidas: el muestreo de
    `propagate_error` va con semilla fija. Sin esto, dos lecturas del
    mismo informe darían números distintos y nadie podría citarlo."""
    payload = view("profile_right", {**FRANKFORT, **THIRDS_CLEAN})
    assert json.dumps(audit(payload), sort_keys=True) == json.dumps(
        audit(payload), sort_keys=True
    )


def test_el_sello_de_captura_ensancha_la_banda():
    """`GRADE_FACTOR`: un selfie a distancia de brazo paga en anchura de
    banda, no en un aviso que se pueda ignorar."""
    limpio = audit(view("profile_right", {**FRANKFORT, **THIRDS_CLEAN}, grade="A"))
    malo = audit(view("profile_right", {**FRANKFORT, **THIRDS_CLEAN}, grade="C"))

    (a,) = by_name(limpio, "upper_third_pct")
    (c,) = by_name(malo, "upper_third_pct")
    assert c["errorBand"] > a["errorBand"]


# ──────────────────────── control cruzado ────────────────────────

NASAL = {
    "nasion": [[52.0, 39.5], [52.0, 40.5]],
    "pronasale": [[75.5, 72.0], [76.5, 72.0]],
    "alar_crease": [[52.5, 74.0], [53.5, 74.0]],
    "subnasale": [[49.5, 60.0], [50.5, 60.0]],
    "columella_apex": [[60.0, 50.0]],
    "labrale_superius": [[40.0, 50.0]],
}


def test_los_dos_perfiles_producen_control_cruzado():
    body = audit(
        view("profile_right", {**FRANKFORT, **NASAL}),
        view("profile_left", {**FRANKFORT, **NASAL}),
    )

    cruces = {c["metric"] for c in body["crossChecks"]}
    assert "goode_ratio" in cruces

    goode = next(c for c in body["crossChecks"] if c["metric"] == "goode_ratio")
    # Mismo marcado en los dos lados: no pueden discrepar.
    assert goode["difference"] == pytest.approx(0.0, abs=1e-9)
    assert goode["verdict"] == "concordant"


def test_un_solo_perfil_no_produce_control_cruzado():
    """Media razón de ser de la segunda foto: sin ella no hay con qué
    distinguir asimetría real de error de marcado."""
    body = audit(view("profile_right", {**FRANKFORT, **NASAL}))
    assert body["crossChecks"] == []


def test_la_misma_metrica_sale_etiquetada_con_su_vista():
    body = audit(
        view("profile_right", {**FRANKFORT, **NASAL}),
        view("profile_left", {**FRANKFORT, **NASAL}),
    )
    vistas = {m["view"] for m in by_name(body, "goode_ratio")}
    assert vistas == {"profile_right", "profile_left"}


# ──────────────────────── validación ────────────────────────


def test_sin_la_pareja_de_escala_el_error_dice_cual_falta():
    response = client.post(
        "/audit", json={"views": [view("profile_right", THIRDS_CLEAN)]}
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "porion" in detail and "orbitale" in detail


def test_una_marca_fuera_del_encuadre_se_rechaza():
    """Suele significar que el cliente normalizó mal o mezcló dos
    imágenes. El motor lo aceptaría y daría una medida plausible y
    falsa."""
    fuera = {**FRANKFORT, **THIRDS_CLEAN, "menton": [[50.0, 900.0]]}
    response = client.post("/audit", json={"views": [view("profile_right", fuera)]})
    assert response.status_code == 422
    assert "menton" in json.dumps(response.json())


def test_tres_pasadas_no_existen():
    tres = {**FRANKFORT, "subnasale": [[50.0, 60.0], [50.0, 61.0], [50.0, 62.0]]}
    response = client.post("/audit", json={"views": [view("profile_right", tres)]})
    assert response.status_code == 422


def test_un_punto_desconocido_se_rechaza():
    response = client.post(
        "/audit",
        json={"views": [view("profile_right", {**FRANKFORT, "nariz": [[1.0, 2.0]]})]},
    )
    assert response.status_code == 422


def test_una_vista_desconocida_se_rechaza():
    response = client.post(
        "/audit", json={"views": [view("selfie", {**FRANKFORT, **THIRDS_CLEAN})]}
    )
    assert response.status_code == 422


def test_la_misma_vista_dos_veces_se_rechaza():
    """Dos marcados de la misma foto son dos verdades sobre lo mismo, y
    el segundo pisaría al primero en silencio."""
    response = client.post(
        "/audit",
        json={
            "views": [
                view("profile_right", {**FRANKFORT, **THIRDS_CLEAN}),
                view("profile_right", {**FRANKFORT, **THIRDS_DIRTY}),
            ]
        },
    )
    assert response.status_code == 422
    assert "profile_right" in json.dumps(response.json())


def test_campos_de_mas_se_rechazan():
    """`extra="forbid"`: un cliente que envía `capture_grade` en vez de
    `captureGrade` se entera aquí y no con un sello "A" por defecto."""
    payload = view("profile_right", {**FRANKFORT, **THIRDS_CLEAN})
    payload["capture_grade"] = "C"
    response = client.post("/audit", json={"views": [payload]})
    assert response.status_code == 422


# ──────────── lo que hoy NO se puede medir, y por qué ────────────


def test_los_tercios_en_frontal_no_son_calculables_todavia():
    """Colisión real entre dos piezas del motor, dejada a la vista.

    `REGISTRY` declara los tres tercios con `views` que incluyen
    FRONTAL_REST, pero también con `needs_frankfort=True`. Alinear a
    Frankfort exige Porion y Orbitale, que `landmarks.py` clasifica como
    puntos de PERFIL. Resultado: pedidos sobre una frontal, los tres
    salen «no calculables» por puntos que faltan.

    El frontend lo esquiva midiendo los tercios en el perfil derecho
    (ver `web/src/lib/marking/protocol.ts`). Este test fija la conducta
    actual para que, el día que alguien decida —o que la frontal deje de
    necesitar Frankfort, o que Porion y Orbitale se declaren marcables
    de frente— el cambio sea deliberado y no un efecto colateral.
    """
    frontal = {
        "endocanthion_l": [[70.0, 45.0]],
        "endocanthion_r": [[130.0, 45.0]],
        **THIRDS_CLEAN,
    }
    body = audit(view("frontal_rest", frontal))

    for name in ("upper_third_pct", "middle_third_pct", "lower_third_pct"):
        (metric,) = by_name(body, name)
        assert metric["status"] == "not_computable", metric
        assert metric["reason"] == "missing_points"


def test_la_frontal_ya_habilita_sus_cuatro_medidas():
    """Durante meses este test afirmaba lo contrario —«la frontal no
    habilita ninguna métrica todavía»— y estaba bien que lo afirmara:
    era el hueco más grande del motor. Las cuatro frontales se miden
    contra la línea intercantal, no contra Frankfort, así que no chocan
    con lo de arriba."""
    frontal = {
        "endocanthion_r": [[85.0, 80.0]],
        "endocanthion_l": [[115.0, 80.0]],
        "exocanthion_r": [[57.0, 77.0]],
        "exocanthion_l": [[143.0, 77.0]],
        "zygion_r": [[40.0, 100.0]],
        "zygion_l": [[160.0, 100.0]],
        "nasion": [[100.0, 78.0], [100.0, 78.5]],
        "subnasale": [[101.0, 120.0], [101.0, 120.5]],
        "gnathion": [[100.0, 182.0], [100.0, 182.5]],
        "menton": [[100.0, 185.0], [100.0, 185.5]],
    }
    body = audit(view("frontal_rest", frontal))
    for name in ("horizontal_fifths", "facial_index", "midline_deviation", "canthal_tilt"):
        (metric,) = by_name(body, name)
        assert metric["status"] == "reported", metric


# ──────────────────────── el resumen ────────────────────────


def test_la_respuesta_trae_un_resumen_en_lenguaje_llano():
    """El informe no puede empezar por una tabla de estados. Lo que el
    servidor añade es la única parte que exige mirar todas las medidas a
    la vez, y por eso no es trabajo de la capa de presentación."""
    body = audit(view("profile_right", {**FRANKFORT, **THIRDS_CLEAN}))

    assert body["summary"]
    assert "reported" not in body["summary"]
    assert "_" not in body["summary"]
    #: Sin proveedor configurado, el texto es el del motor — y se dice.
    assert body["summarySource"] in ("engine", "agent")


def test_el_resumen_habla_el_idioma_que_se_le_pide():
    response = client.post(
        "/audit",
        json={
            "views": [view("profile_right", {**FRANKFORT, **THIRDS_CLEAN})],
            "locale": "en",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "photographs" in body["summary"] or "measured" in body["summary"]

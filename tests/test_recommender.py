"""El recomendador y el revisor de seguridad: las reglas, una por test.

Esto es lo que impide que el sistema proponga una cirugía por una
proporción que se sale un poco, o un relleno sobre piel inflamada. Cada
regla de docs/02 §4 tiene aquí su test, escrito con el caso que la
justifica.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from frankfort.api.app import app
from frankfort.knowledge import KNOWLEDGE
from frankfort.narrative import Measured
from frankfort.recommender import (
    OBSERVATION_OPTIONS,
    PRICES,
    ObservationIn,
    build_plan,
    cost_category,
    write_intro,
)


def m(value: float, band: float = 1.0, low: float = 90.0, high: float = 110.0,
      name: str = "nasolabial_angle") -> Measured:
    inside = low <= value <= high
    w = high - low
    off = 0.0 if inside else ((value - high) / w if value > high else (low - value) / w)
    return Measured(name=name, value=value, unit="deg", band=band, low=low, high=high,
                    inside=inside, side="none" if inside else ("low" if value < low else "high"),
                    off=off)


# ─────────────────── las reglas ───────────────────


def test_la_escalera_va_de_lo_gratis_a_lo_medico():
    plan = build_plan([m(80.0, low=90, high=110)], [ObservationIn("acne_marks", "clear", True)])
    levels = [s.level for s in plan.steps]
    assert levels == sorted(levels)
    assert levels[0] == 0


def test_poco_fuera_no_llega_a_lo_medico():
    """Un cuarto de rango fuera: hasta cosmético, nada más."""
    plan = build_plan([m(85.0)], [])
    assert plan.steps and max(s.level for s in plan.steps) <= 1


def test_muy_fuera_puede_mencionar_cirugia():
    plan = build_plan([m(50.0)], [])
    assert any(s.level == 3 for s in plan.steps)


def test_dentro_del_rango_no_genera_nada():
    assert build_plan([m(100.0)], []).steps == []


def test_en_el_borde_el_revisor_lo_retira_y_dice_por_que():
    """Una cifra cuyo margen cruza el borde puede estar dentro. No se
    recomienda nada, y lo que se habría recomendado sale en la lista del
    revisor con el motivo."""
    #: Inclinación de ojos de −1° con ±3°: puede ser +2°, dentro.
    plan = build_plan([m(-1.0, band=3.0, low=0.0, high=8.0, name="canthal_tilt")], [])
    assert plan.steps == []
    assert plan.vetoed and all("borde" in v.why for v in plan.vetoed)


def test_una_observacion_nunca_llega_a_cirugia():
    for tag, opts in OBSERVATION_OPTIONS.items():
        assert all(o.level <= 2 for o in opts), tag


def test_una_observacion_de_una_sola_foto_se_queda_en_cosmetico():
    plan = build_plan([], [ObservationIn("acne_marks", "clear", corroborated=False)])
    assert max(s.level for s in plan.steps) <= 1


def test_una_observacion_probable_tampoco_pasa_de_cosmetico():
    plan = build_plan([], [ObservationIn("acne_marks", "probable", corroborated=True)])
    assert max(s.level for s in plan.steps) <= 1


def test_una_observacion_dudosa_no_genera_pasos():
    assert build_plan([], [ObservationIn("acne_marks", "uncertain", True)]).steps == []


def test_lo_que_no_pide_nada_no_genera_pasos():
    """«Piel uniforme» o «pómulos marcados» son observaciones, no problemas."""
    plan = build_plan([], [ObservationIn("skin_even", "clear", True),
                           ObservationIn("malar_prominent", "clear", True)])
    assert plan.steps == []


def test_primero_la_piel():
    """Con granos inflamados, lo médico sobre el resto de la cara se
    pospone: la mayoría de especialistas no pinchan sobre piel activa."""
    plan = build_plan(
        [m(50.0)],  # muy fuera: genera nivel 2 y 3
        [ObservationIn("acne_active", "clear", corroborated=True)],
    )
    medical_not_skin = [s for s in plan.steps if s.level >= 2 and s.source.startswith("metric:")]
    assert medical_not_skin and all(s.deferred for s in medical_not_skin)
    #: Y lo de la propia piel NO se pospone: es justo lo primero.
    skin = [s for s in plan.steps if s.source == "observation:acne_active"]
    assert skin and not any(s.deferred for s in skin)


def test_sin_piel_activa_no_se_pospone_nada():
    plan = build_plan([m(50.0)], [ObservationIn("acne_marks", "clear", True)])
    assert not any(s.deferred for s in plan.steps)


# ─────────────────── precios ───────────────────


def test_todo_paso_de_pago_tiene_categoria_de_precio():
    """Un paso de nivel 1 o más sin precio es un paso que el plan no
    puede situar: o falta la categoría o falta la regla que la detecta."""
    options = [o for kb in KNOWLEDGE.values() for opts in kb.options.values() for o in opts]
    options += [o for opts in OBSERVATION_OPTIONS.values() for o in opts]
    for o in options:
        if o.level >= 1:
            for loc in ("es", "en"):
                assert cost_category(o.text(loc)), f"sin precio ({loc}): {o.text(loc)[:60]}"


def test_todas_las_categorias_tienen_los_cinco_paises():
    for cat, by_country in PRICES.items():
        assert set(by_country) == {"ES", "MX", "CO", "AR", "US"}, cat
        for lo, hi in by_country.values():
            assert 0 < lo < hi, cat


def test_el_precio_sale_en_la_moneda_del_pais():
    plan = build_plan([m(50.0)], [], country="MX")
    assert plan.currency == "MXN"
    assert any(s.cost for s in plan.steps)


def test_lo_gratis_no_lleva_precio():
    plan = build_plan([m(50.0)], [])
    assert all(s.cost is None for s in plan.steps if s.level == 0)


# ─────────────────── la introducción ───────────────────


class Fake:
    name = "fake"

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, system, user):
        return self.text


def test_la_introduccion_del_agente_se_publica_si_pasa():
    plan = build_plan([m(50.0)], [])
    out = write_intro(plan, "es", Fake(
        "Empieza por lo gratis: muchas veces basta, y sirve para saber si "
        "lo demás hace falta. Lo médico tiene sentido solo después."))
    assert out.intro_source == "agent"


def test_un_precio_inventado_en_la_introduccion_la_tumba():
    plan = build_plan([m(50.0)], [])
    out = write_intro(plan, "es", Fake(
        "Empieza por lo gratis; si no basta, un relleno cuesta unos 400 euros "
        "y suele dar buen resultado en la mayoría de los casos."))
    assert out.intro_source == "engine"


# ─────────────────── la API ───────────────────


def test_el_endpoint_arma_el_plan_desde_las_cifras(monkeypatch):
    monkeypatch.setenv("FRANKFORT_LLM_PROVIDER", "none")
    client = TestClient(app)
    r = client.post("/plan", json={
        "locale": "es", "country": "CO",
        "metrics": [{"name": "nasolabial_angle", "unit": "deg", "value": 60.0,
                     "errorBand": 1.0, "reference": [90.0, 110.0]}],
        "observations": [{"tag": "acne_active", "confidence": "clear",
                          "corroboratingViews": ["frontal_rest"]}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["currency"] == "COP"
    assert [s["level"] for s in body["steps"]] == sorted(s["level"] for s in body["steps"])
    assert any(s["deferred"] for s in body["steps"])
    assert body["intro"]


def test_una_constatacion_no_es_un_paso():
    """«No cambia con hábitos» responde a «¿se puede cambiar?» en la
    tarjeta; en un plan de cosas que hacer no se puede hacer. Salió en
    un plan real como paso «gratis»."""
    plan = build_plan([m(160.0, low=115.0, high=130.0, name="nasofrontal_angle")], [])
    assert not any(s.text.startswith("No cambia con hábitos") for s in plan.steps)
    assert plan.steps  # la cirugía mencionada sigue

"""La explicación personalizada de cada medida, y lo que el agente no puede tocar.

La frontera que vigilan estos tests es la que hace defendible poner un
LLM a hablar de la cara de alguien: el modelo REDACTA —cómo está tu
medida, qué significa— y no DECIDE —qué se te recomienda, cuánto se
puede afirmar—. Lo segundo es determinista, y si alguien lo mueve al
prompt, se entera aquí.
"""

from __future__ import annotations

import json

from frankfort.agents import personalize
from frankfort.insight import allowed_level, build_insight, build_insights, certainty
from frankfort.knowledge import KNOWLEDGE
from frankfort.metrics import REGISTRY
from frankfort.narrative import Brief, Measured


def m(value: float, band: float = 2.0, low: float = 90.0, high: float = 110.0,
      name: str = "nasolabial_angle") -> Measured:
    inside = low <= value <= high
    width = high - low
    off = 0.0 if inside else ((value - high) / width if value > high else (low - value) / width)
    return Measured(
        name=name, value=value, unit="deg", band=band, low=low, high=high,
        inside=inside, side="none" if inside else ("low" if value < low else "high"),
        off=off,
    )


def brief(*ms: Measured, grade: str = "B", locale: str = "es") -> Brief:
    return Brief(locale=locale, grade=grade, measured=ms, dropped=0,  # type: ignore[arg-type]
                 agreements=0, conflicts=0)


# ─────────────────── la base de conocimiento ───────────────────


def test_cada_medida_del_motor_tiene_su_conocimiento_completo():
    """Sin esto, el motor aprende a medir algo y el informe no sabe
    decir qué es ni qué hacer con ello."""
    for spec in REGISTRY:
        kb = KNOWLEDGE[spec.name]
        for loc in ("es", "en"):
            assert kb.what[loc] and kb.inside[loc] and kb.sensitive_to[loc]
            for side in ("low", "high"):
                assert kb.meaning[side][loc]
        for side in ("low", "high"):
            assert kb.options[side], f"{spec.name}/{side} sin opciones"


def test_las_opciones_van_de_menos_a_mas_invasivo():
    for name, kb in KNOWLEDGE.items():
        for side, opts in kb.options.items():
            levels = [o.level for o in opts]
            assert levels == sorted(levels), f"{name}/{side}"


def test_toda_cirugia_remite_al_especialista():
    """Una cirugía mencionada a partir de fotos de móvil sin esta
    coletilla es una recomendación irresponsable."""
    for kb in KNOWLEDGE.values():
        for opts in kb.options.values():
            for o in opts:
                if o.level == 3:
                    assert "especialista" in o.es and "specialist" in o.en


# ─────────────────── certeza y proporcionalidad ───────────────────


def test_fuera_incluso_con_el_margen_es_firme():
    assert certainty(m(120.0, band=3.0)) == "firm"


def test_si_el_margen_cruza_el_borde_no_se_afirma():
    """111° con ±3 puede ser 108°, dentro de lo normal. El sistema no
    puede decir que se sale, y tiene que decirlo así."""
    assert certainty(m(111.0, band=3.0)) == "edge"


def test_dentro_pero_rozando_el_borde_tambien_es_edge():
    assert certainty(m(109.0, band=3.0)) == "edge"
    assert certainty(m(100.0, band=3.0)) == "firm"


def test_la_escalada_es_proporcional():
    """El caso del tercio inferior: ortognática por una proporción un 8 %
    distinta. Salirse un poco no abre la puerta a la cirugía."""
    assert allowed_level(m(100.0)) is None
    assert allowed_level(m(115.0)) == 1       # un cuarto de rango fuera
    assert allowed_level(m(125.0)) == 2       # tres cuartos
    assert allowed_level(m(150.0)) == 3       # dos rangos


def test_dentro_del_rango_no_se_recomienda_nada():
    ins = build_insight(m(100.0), brief(m(100.0)))
    assert ins.options == ()
    assert "nada que corregir" in (ins.no_options or "")


def test_en_el_borde_se_pide_repetir_el_marcado_antes_que_nada():
    """Recomendar algo sobre una cifra que puede estar dentro de lo
    normal es vender una solución a un problema que quizá no existe."""
    x = m(111.0, band=3.0)
    ins = build_insight(x, brief(x))
    assert ins.options == ()
    assert "repite el marcado" in (ins.no_options or "")


def test_poco_fuera_no_llega_a_la_cirugia():
    x = m(115.0, band=1.0)
    ins = build_insight(x, brief(x))
    assert ins.options
    assert max(o.level for o in ins.options) <= 1


def test_muy_fuera_menciona_que_existe_cirugia():
    x = m(150.0, band=1.0)
    ins = build_insight(x, brief(x))
    assert any(o.level == 3 for o in ins.options)


# ─────────────────── la lectura personalizada ───────────────────


def test_la_lectura_dice_la_cifra_el_rango_y_la_certeza():
    x = m(120.0, band=2.0)
    ins = build_insight(x, brief(x))
    assert "120,0°" in ins.reading
    assert "90,0°" in ins.reading and "110,0°" in ins.reading
    assert "no es cosa del margen" in ins.reading


def test_con_fotos_justas_dice_que_distorsiona_esa_medida():
    x = m(120.0)
    ins = build_insight(x, brief(x, grade="C"))
    assert KNOWLEDGE["nasolabial_angle"].sensitive_to["es"] in ins.reading


def test_el_acuerdo_entre_perfiles_entra_en_la_lectura():
    x = m(100.0)
    [ins] = build_insights(brief(x), {"nasolabial_angle": "concordant"})
    assert "dan lo mismo" in ins.reading


# ─────────────────── el agente ───────────────────


class Fake:
    name = "fake"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def complete_json(self, system: str, user: str) -> str:
        self.calls += 1
        self.seen = json.loads(user)
        return json.dumps(self.payload, ensure_ascii=False)


def test_una_sola_llamada_para_todas_las_medidas():
    """Presupuesto (docs/03) y calidad: el agente relaciona medidas entre
    sí solo si las ve juntas."""
    a, b = m(100.0), m(120.0, name="nasofrontal_angle", low=115.0, high=130.0)
    fake = Fake({"metrics": {}})
    personalize(build_insights(brief(a, b), {}), brief(a, b), fake)
    assert fake.calls == 1
    assert set(fake.seen["metrics"]) == {"nasolabial_angle", "nasofrontal_angle"}


def test_lo_que_redacta_bien_el_agente_se_publica():
    x = m(120.0, band=2.0)
    fake = Fake({"metrics": {"nasolabial_angle": {
        "reading": "Tu ángulo entre la nariz y el labio sale 120,0°, por encima de lo habitual, y tu margen no lo cambia.",
        "meaning": "Quiere decir que la punta de tu nariz mira hacia arriba al verte de perfil.",
    }}})
    [ins] = personalize(build_insights(brief(x), {}), brief(x), fake).insights
    assert ins.source == "agent"
    assert "mira hacia arriba" in ins.meaning


def test_un_numero_inventado_devuelve_ese_campo_al_motor():
    x = m(120.0, band=2.0)
    base = build_insight(x, brief(x))
    fake = Fake({"metrics": {"nasolabial_angle": {
        "reading": "Tu ángulo sale unos 118 grados, bastante por encima de lo que se ve normalmente.",
        "meaning": "Quiere decir que la punta de tu nariz mira hacia arriba al verte de perfil.",
    }}})
    out = personalize([base], brief(x), fake)
    [ins] = out.insights
    assert ins.reading == base.reading          # el campo malo, del motor
    assert "mira hacia arriba" in ins.meaning    # el bueno se conserva
    assert "número inventado" in out.rejected["nasolabial_angle.reading"]


def test_en_el_borde_el_agente_no_puede_afirmar():
    """Si el margen cruza el borde, un «claramente por encima» desmiente
    el cálculo que se hizo justo para no afirmarlo."""
    x = m(111.0, band=3.0)
    base = build_insight(x, brief(x))
    fake = Fake({"metrics": {"nasolabial_angle": {
        "reading": "Tu ángulo sale 111,0° y está claramente por encima de lo que es habitual para la gente.",
        "meaning": "Quiere decir que la punta de tu nariz apunta algo hacia arriba de perfil.",
    }}})
    [ins] = personalize([base], brief(x), fake).insights
    assert ins.reading == base.reading


def test_el_agente_no_toca_las_opciones_ni_el_que_es():
    """Aunque devuelva esos campos, se ignoran: qué se te recomienda lo
    decide la regla de proporcionalidad, no el modelo."""
    x = m(115.0, band=1.0)
    base = build_insight(x, brief(x))
    fake = Fake({"metrics": {"nasolabial_angle": {
        "reading": "Tu ángulo sale 115,0°, por encima de lo habitual aunque por poco.",
        "meaning": "La punta de tu nariz mira algo hacia arriba cuando te ven de perfil.",
        "what": "otra cosa",
        "options": [{"level": 3, "text": "cirugía ya"}],
    }}})
    [ins] = personalize([base], brief(x), fake).insights
    assert ins.what == base.what
    assert ins.options == base.options


def test_si_el_proveedor_revienta_quedan_las_del_motor():
    class Caido:
        name = "fake"

        def complete_json(self, system: str, user: str) -> str:
            raise OSError("reset")

    x = m(120.0)
    base = build_insights(brief(x), {})
    out = personalize(base, brief(x), Caido())
    assert out.insights == base
    assert "*" in out.rejected


def test_json_roto_tampoco_tumba_el_informe():
    class Roto:
        name = "fake"

        def complete_json(self, system: str, user: str) -> str:
            return "```json\n{no es json"

    x = m(120.0)
    base = build_insights(brief(x), {})
    assert personalize(base, brief(x), Roto()).insights == base


def test_la_plantilla_contrae_de_el_en_del():
    """«depende de el giro de la cabeza» salió en un informe real."""
    for name, kb in KNOWLEDGE.items():
        x = m(200.0, name=name)
        ins = build_insight(x, brief(x, grade="C"))
        assert " de el " not in ins.reading, name

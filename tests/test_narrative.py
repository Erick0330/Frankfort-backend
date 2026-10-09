"""El resumen en lenguaje llano, y la correa del agente.

Estos tests existen porque el informe anterior era correcto e
ilegible: enumeraba estados, motivos de supresión y bandas, y no decía
en ninguna parte qué había salido. Lo que se comprueba aquí es lo
contrario de lo habitual — no que las cuentas cuadren, sino que el texto
diga algo y no diga lo que no debe.
"""

from __future__ import annotations

import pytest

from frankfort.agents import Explanation, explain, verify
from frankfort.auditor import AuditReport, MetricResult, Status
from frankfort.landmarks import Point
from frankfort.metrics import REGISTRY
from frankfort.narrative import (
    PLAIN_NAMES,
    Brief,
    Measured,
    build_brief,
    plain_name,
    summarize,
)


def measured(
    name: str = "nasolabial_angle",
    value: float = 95.0,
    low: float = 90.0,
    high: float = 110.0,
    band: float = 3.0,
) -> Measured:
    inside = low <= value <= high
    return Measured(
        name=name,
        value=value,
        unit="deg",
        band=band,
        low=low,
        high=high,
        inside=inside,
        side="none" if inside else ("low" if value < low else "high"),
    )


def brief(**kw) -> Brief:
    base = dict(
        locale="es",
        grade="B",
        measured=(measured(),),
        dropped=0,
        agreements=0,
        conflicts=0,
    )
    base.update(kw)
    return Brief(**base)  # type: ignore[arg-type]


# ─────────────────── nombres llanos ───────────────────


def test_todas_las_metricas_del_motor_tienen_nombre_llano():
    """Si el motor aprende a medir algo nuevo, el resumen tiene que
    saber nombrarlo. Sin esto, la primera frase del informe diría
    'mandibular_plane_angle se sale del rango', que es exactamente el
    problema que este módulo vino a arreglar."""
    for spec in REGISTRY:
        for locale in ("es", "en"):
            assert PLAIN_NAMES.get(spec.name, {}).get(locale), (
                f"{spec.name} sin nombre llano en {locale}"
            )


def test_el_nombre_llano_no_es_el_identificador():
    assert plain_name("nasolabial_angle", "es") != "nasolabial_angle"


# ─────────────────── el resumen ───────────────────


def test_dice_cuantas_medidas_hay_y_cuantas_son_normales():
    texto = summarize(
        brief(measured=(measured(), measured("goode_ratio", 0.57, 0.55, 0.60, 0.02)))
    )
    assert "2 cosas" in texto
    assert "dentro de lo habitual" in texto


def test_nombra_la_que_se_sale_y_hacia_donde():
    texto = summarize(brief(measured=(measured(value=125.0),)))
    assert plain_name("nasolabial_angle", "es") in texto
    assert "por arriba" in texto


def test_sin_medidas_no_finge_un_informe():
    """Lo peor que puede hacer aquí es redactar un párrafo bonito sobre
    la nada. Dice que no hay nada y dónde se consigue."""
    texto = summarize(brief(measured=()))
    assert "marca" in texto.lower()


def test_el_acuerdo_entre_lados_se_dice_en_cristiano():
    texto = summarize(brief(agreements=2))
    assert "una fotografía suelta" in texto


def test_un_desacuerdo_entre_lados_pesa_mas_que_el_acuerdo():
    """Si los dos perfiles no coinciden, eso es lo que hay que contar,
    no que otras dos medidas sí coincidieran."""
    texto = summarize(brief(agreements=2, conflicts=1))
    assert "no dan lo mismo" in texto
    assert "una fotografía suelta" not in texto


def test_el_resumen_nunca_habla_de_lo_que_no_se_pudo_medir():
    """Decisión de producto: una lista de métricas caídas con su motivo
    técnico no le sirve a quien lee. El número se publica aparte y en
    pequeño; el resumen es para lo que SÍ se midió."""
    texto = summarize(brief(dropped=7))
    assert "7" not in texto


def test_hay_resumen_en_ingles():
    texto = summarize(brief(locale="en", measured=(measured(value=125.0),)))
    assert "high side" in texto
    assert "cosas" not in texto


# ─────────────────── los hechos ───────────────────


def _report(*results: MetricResult) -> AuditReport:
    return AuditReport(
        metrics=list(results),
        unreliable_points=(),
        missing_double_marks=(),
    )


def _result(name: str, status: Status, value: float | None = 95.0) -> MetricResult:
    return MetricResult(
        name=name,
        unit="deg",
        status=status,
        value=value,
        error_band=3.0,
        deviation=0.0,
        reference=(90.0, 110.0),
        depends_on=(Point.SUBNASALE,),
    )


def test_solo_entran_las_publicables():
    b = build_brief(
        {
            "profile_right": _report(
                _result("nasolabial_angle", Status.REPORTED),
                _result("goode_ratio", Status.SUPPRESSED, None),
                _result("nasofrontal_angle", Status.NOT_COMPUTABLE, None),
            )
        },
        [],
    )
    assert [m.name for m in b.measured] == ["nasolabial_angle"]
    assert b.dropped == 2


def test_la_misma_metrica_en_los_dos_perfiles_sale_una_vez():
    """Al lector le da igual de qué fotografía salió, y verla dos veces
    con dos cifras parecidas sugiere una contradicción que no existe."""
    b = build_brief(
        {
            "profile_right": _report(_result("nasolabial_angle", Status.REPORTED)),
            "profile_left": _report(_result("nasolabial_angle", Status.REPORTED)),
        },
        [],
    )
    assert len(b.measured) == 1


def test_lo_que_se_sale_va_primero():
    b = build_brief(
        {
            "profile_right": _report(
                _result("nasolabial_angle", Status.REPORTED, 95.0),
                _result("nasofrontal_angle", Status.REPORTED, 200.0),
            )
        },
        [],
    )
    assert b.measured[0].name == "nasofrontal_angle"


# ─────────────────── la correa del agente ───────────────────


def test_un_numero_inventado_tumba_el_texto():
    """El fallo más probable de un LLM redactando sobre medidas: una
    cifra plausible que el motor no ha calculado. Contradice al informe
    en el mismo informe."""
    b = brief()
    malo = (
        "Tu ángulo entre la nariz y el labio es de 97 grados, que entra "
        "dentro de lo normal y no hay nada raro que contar sobre ello."
    )
    assert verify(malo, b) is not None


def test_las_cifras_del_motor_si_se_pueden_repetir():
    b = brief()
    bueno = (
        "Se midió una cosa en tus fotos: el ángulo entre la nariz y el "
        "labio, que sale 95 grados con un margen de 3. Eso queda dentro "
        "de lo habitual, que va de 90 a 110. No es una nota: es una "
        "proporción con su margen."
    )
    assert verify(bueno, b) is None


@pytest.mark.parametrize(
    "texto",
    [
        "Tu perfil es armónico y equilibrado, con proporciones agradables "
        "que encajan bien entre sí según lo medido en las fotografías.",
        "Estos valores sugieren una posible patología del tabique que "
        "convendría revisar con un especialista antes de seguir midiendo.",
        "Tu cara tiene una puntuación alta en proporciones y eso se nota "
        "en el conjunto de las medidas tomadas sobre las fotografías.",
    ],
)
def test_ni_juicios_esteticos_ni_diagnosticos(texto: str):
    """Las dos cosas que un modelo añade solo si le dejas, y las dos que
    este producto no puede publicar: la portada promete que no hay
    puntuación, y un diagnóstico es una promesa que no puede cumplir."""
    assert verify(texto, brief()) is not None


def test_ni_listas_ni_titulares():
    malo = "- Se midió una cosa\n- Está dentro de lo normal\n- Nada más"
    assert verify(malo, brief()) is not None


def test_sin_proveedor_se_publica_el_del_motor():
    out = explain(brief(), None)
    assert out.source == "engine"
    assert out.text == summarize(brief())


def test_con_proveedor_bueno_se_publica_el_del_agente():
    class Bueno:
        name = "fake"

        def complete(self, system: str, user: str) -> str:
            return (
                "Medimos una sola cosa en tus fotos: el ángulo entre la "
                "nariz y el labio. Sale 95 grados, con un margen de 3 "
                "arriba o abajo. Lo habitual va de 90 a 110, así que cae "
                "dentro. No es una nota, es una proporción."
            )

    out = explain(brief(), Bueno())
    assert out.source == "agent"
    assert "95" in out.text


def test_si_el_agente_se_inventa_algo_gana_el_motor():
    class Mentiroso:
        name = "fake"

        def complete(self, system: str, user: str) -> str:
            return (
                "Tu ángulo nasolabial es de 97,4 grados y tu perfil "
                "resulta armónico, con una proporción muy cercana a lo "
                "ideal en todas las medidas tomadas."
            )

    out = explain(brief(), Mentiroso())
    assert out.source == "engine"
    assert out.rejected


def test_si_el_proveedor_revienta_el_informe_no_se_cae():
    """Un free tier tiene malos días. Un informe que depende de que un
    tercero conteste no es un informe."""

    class Caido:
        name = "fake"

        def complete(self, system: str, user: str) -> str:
            raise OSError("connection reset")

    out = explain(brief(), Caido())
    assert isinstance(out, Explanation)
    assert out.source == "engine"
    assert out.text


def test_con_muchas_fuera_de_rango_no_las_enumera_todas():
    """Siete nombres en una frase es una frase que nadie termina. Se
    nombran las tres que más se salen y el resto se cuenta."""
    fuera = tuple(
        measured(name=n, value=200.0)
        for n in (
            "nasolabial_angle",
            "nasofrontal_angle",
            "facial_convexity_angle",
            "upper_third_pct",
            "middle_third_pct",
        )
    )
    texto = summarize(brief(measured=fuera))
    assert "Otras 2" in texto
    assert texto.count("(por arriba)") == 3

"""La explicación personalizada de cada medida, en su versión determinista.

── Qué es "personalizada" aquí ──────────────────────────────────
Una explicación genérica dice «el ángulo nasolabial mide hacia dónde
apunta la nariz». Una personalizada dice «el tuyo sale 118°, por encima
de lo habitual — y aunque hubieras marcado con el error máximo que tu
propio doble marcado permite, seguiría por encima». La segunda frase es la
que vale, y sale de CRUZAR tres cosas que el sistema ya tiene:

  · la cifra y su banda de error (el motor),
  · el rango de la población (el registro),
  · lo que significa cada lado del rango (knowledge.py).

Este módulo hace ese cruce con plantillas. El agente (`agents.personalize`)
lo redacta mejor; si no hay agente, esto se publica tal cual.

── La certeza: lo que ningún informe de la competencia dice ──────
Con la banda en la mano se puede decir algo que una cifra suelta no dice:
si la conclusión SOBREVIVE al error de medición.

  · `firm`: incluso en el peor caso del margen, la medida sigue del mismo
    lado del rango.
  · `edge`: el margen cruza el borde del rango. Puede estar dentro o
    fuera, y no se puede afirmar ninguna de las dos cosas.

Una medida `edge` no recibe opciones de cambio. Recomendar algo sobre
una cifra que puede estar dentro de lo normal sería vender una solución
a un problema que quizá no existe, y la primera recomendación honesta ahí
es repetir el marcado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .knowledge import KNOWLEDGE, Level, Locale
from .narrative import Brief, Measured, plain_name

Certainty = Literal["firm", "edge"]
Position = Literal["inside", "low", "high"]


def allowed_level(m: Measured) -> Level | None:
    """Hasta qué nivel de intervención se puede hablar, según cuánto se sale.

    Es la escalada proporcional del `safety_reviewer` (docs/02 §4) hecha
    regla, y deliberadamente FUERA del alcance del LLM:

      · dentro del rango            → ninguno: no hay nada que corregir;
      · se sale menos de medio rango → hasta cosmético;
      · hasta rango y medio          → hasta médico sin cirugía;
      · más                          → se menciona que existe la cirugía.

    `off` va en anchos del propio rango de referencia, así que la regla
    es la misma para un ángulo en grados que para un porcentaje.
    """
    if m.inside:
        return None
    if m.off <= 0.5:
        return 1
    if m.off <= 1.5:
        return 2
    return 3


def certainty(m: Measured) -> Certainty:
    """¿La conclusión aguanta el margen de error?"""
    lo, hi = m.value - m.band, m.value + m.band
    if m.inside:
        return "firm" if lo >= m.low and hi <= m.high else "edge"
    if m.side == "high":
        return "firm" if lo > m.high else "edge"
    return "firm" if hi < m.low else "edge"


@dataclass(frozen=True, slots=True)
class OptionOut:
    level: Level
    text: str


@dataclass(frozen=True, slots=True)
class Insight:
    name: str
    #: Qué es la medida. Del conocimiento, no se personaliza.
    what: str
    #: Cómo está LA TUYA: cifra, rango y certeza.
    reading: str
    #: Qué quiere decir eso en lo que se ve.
    meaning: str
    position: Position
    certainty: Certainty
    #: Lo que se puede hacer, ya filtrado por proporcionalidad.
    options: tuple[OptionOut, ...]
    #: Por qué no hay opciones, cuando no las hay.
    no_options: str | None
    #: `engine` o `agent`: quién redactó `reading` y `meaning`.
    source: Literal["engine", "agent"] = "engine"


def _fmt(value: float, unit: str, locale: Locale) -> str:
    """Como lo formatea el cliente (`formatValue`): mismo redondeo."""
    if unit == "ratio":
        #: Tres decimales, como el motor (`auditor._fmt`) y el cliente: con
        #: dos, la tarjeta ponía 0,523 en grande y la frase de debajo 0,52.
        text = f"{value:.3f}"
    else:
        text = f"{value:.1f}"
    if locale == "es":
        text = text.replace(".", ",")
    suffix = {"deg": "°", "percent": " %", "ratio": ""}.get(unit, "")
    return text + suffix


_T: dict[Locale, dict[str, str]] = {
    "es": {
        "value": "El tuyo sale {value}, y lo habitual va de {low} a {high}.",
        "inside_firm": " Está dentro, y con margen: aunque tu marcado se hubiera desviado lo máximo que permite su error ({band}), seguiría dentro.",
        "inside_edge": " Está dentro, aunque cerca del borde: con tu margen de error ({band}) no se puede descartar que se salga un poco.",
        "out_firm_high": " Está por encima, y no es cosa del margen: incluso restándole todo el error de tu marcado ({band}), seguiría por encima.",
        "out_firm_low": " Está por debajo, y no es cosa del margen: incluso sumándole todo el error de tu marcado ({band}), seguiría por debajo.",
        "out_edge_high": " Sale por encima, pero por poco: tu margen de error ({band}) llega hasta dentro de lo habitual, así que no se puede afirmar.",
        "out_edge_low": " Sale por debajo, pero por poco: tu margen de error ({band}) llega hasta dentro de lo habitual, así que no se puede afirmar.",
        "agree": " Lo mediste en los dos perfiles y dan lo mismo.",
        "differ": " Ojo: tus dos perfiles no dan lo mismo.",
        "photo": " Con fotos de calidad justa, ten en cuenta que esta medida depende de {what}",
        "no_inside": "Está dentro de lo habitual: no hay nada que corregir.",
        "no_edge": "Está tan cerca del borde que tu margen no permite afirmar que se salga. Antes de pensar en cambiar nada, repite el marcado de este módulo: si sale igual, ya es un dato.",
    },
    "en": {
        "value": "Yours comes out at {value}, and the usual range runs from {low} to {high}.",
        "inside_firm": " It is inside, with room to spare: even if your marking had drifted as far as its error allows ({band}), it would still be inside.",
        "inside_edge": " It is inside, though near the edge: with your error margin ({band}) it could be slightly out.",
        "out_firm_high": " It is above, and not because of the margin: even taking away all your marking error ({band}), it would still be above.",
        "out_firm_low": " It is below, and not because of the margin: even adding all your marking error ({band}), it would still be below.",
        "out_edge_high": " It comes out above, but only just: your error margin ({band}) reaches into the usual range, so it cannot be claimed.",
        "out_edge_low": " It comes out below, but only just: your error margin ({band}) reaches into the usual range, so it cannot be claimed.",
        "agree": " You measured it on both profiles and they agree.",
        "differ": " Careful: your two profiles disagree.",
        "photo": " With photos on the poor side, bear in mind this measure depends on {what}",
        "no_inside": "It is inside the usual range: there is nothing to correct.",
        "no_edge": "It is so close to the edge that your margin cannot say it is out. Before thinking about changing anything, redo the marking for this module: if it comes out the same, that is real information.",
    },
}


def build_insight(
    m: Measured,
    brief: Brief,
    *,
    cross: Literal["agree", "differ"] | None = None,
) -> Insight:
    """La explicación de UNA medida, con plantillas."""
    kb = KNOWLEDGE[m.name]
    loc = brief.locale
    t = _T[loc]
    f = lambda v: _fmt(v, m.unit, loc)  # noqa: E731

    cert = certainty(m)
    position: Position = "inside" if m.inside else m.side  # type: ignore[assignment]

    parts = [t["value"].format(value=f(m.value), low=f(m.low), high=f(m.high))]
    band = f(m.band)
    if m.inside:
        parts.append(t[f"inside_{cert}"].format(band=band))
    else:
        parts.append(t[f"out_{cert}_{m.side}"].format(band=band))
    if cross == "agree":
        parts.append(t["agree"])
    elif cross == "differ":
        parts.append(t["differ"])
    if brief.grade == "C":
        sentence = t["photo"].format(what=kb.sensitive_to[loc])
        #: «depende de el giro» → «depende del giro». La contracción es
        #: obligatoria en castellano y la plantilla no sabe con qué
        #: artículo empieza cada texto de la base de conocimiento.
        if loc == "es":
            sentence = sentence.replace(" de el ", " del ")
        parts.append(sentence)

    meaning = kb.inside[loc] if m.inside else kb.meaning[m.side][loc]  # type: ignore[index]

    level = allowed_level(m)
    options: tuple[OptionOut, ...] = ()
    no_options: str | None
    if m.inside:
        no_options = t["no_inside"]
    elif cert == "edge":
        #: Sobre una cifra que puede estar dentro de lo normal no se
        #: recomienda nada. Ver el docstring del módulo.
        no_options = t["no_edge"]
    else:
        no_options = None
        options = tuple(
            OptionOut(level=o.level, text=o.text(loc))
            for o in kb.options[m.side]  # type: ignore[index]
            if level is not None and o.level <= level
        )

    return Insight(
        name=m.name,
        what=kb.what[loc],
        reading="".join(parts),
        meaning=meaning,
        position=position,
        certainty=cert,
        options=options,
        no_options=no_options,
    )


def build_insights(
    brief: Brief,
    verdicts: dict[str, str],
) -> list[Insight]:
    """Una explicación por medida publicable, en el orden del resumen.

    `verdicts` es el veredicto del control cruzado por métrica, cuando lo
    hubo: `concordant` se dice como acuerdo y cualquier otro como
    desacuerdo — el detalle de por qué no coinciden no le sirve a quien
    lee, lo que le sirve es saber que no puede fiarse todavía.
    """
    out = []
    for m in brief.measured:
        #: Una métrica sin conocimiento escrito no tumba el informe: sale
        #: sin explicación personalizada y la tarjeta cae a la genérica.
        #: El test de cobertura de `test_insight.py` es el que obliga a
        #: escribirla — en producción, un 500 por eso sería peor.
        if m.name not in KNOWLEDGE:
            continue
        v = verdicts.get(m.name)
        cross = None if v is None else ("agree" if v == "concordant" else "differ")
        out.append(build_insight(m, brief, cross=cross))
    return out


__all__ = [
    "Insight",
    "OptionOut",
    "allowed_level",
    "build_insight",
    "build_insights",
    "certainty",
    "plain_name",
]

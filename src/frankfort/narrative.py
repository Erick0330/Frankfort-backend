"""De las medidas al castellano: los hechos del informe y su resumen.

── Qué problema resuelve ────────────────────────────────────────
El informe sabía decir `nasolabial_angle · 95.4° ±3.1 · reported ·
deviation 0.0` y no sabía decir «el ángulo entre la nariz y el labio te
sale dentro de lo normal». Lo primero es correcto y lo segundo es lo
único que le sirve a quien no ha medido una cara en su vida.

── La división del trabajo ──────────────────────────────────────
Este módulo produce dos cosas, y la distinción importa:

1. `Brief` — los HECHOS. Números ya calculados por el motor, sin prosa.
   Es lo que se le enseña al agente, y es lo único de lo que puede
   hablar.
2. `summarize()` — un resumen en prosa llana construido con plantillas,
   determinista y sin red.

El agente (ver `agents.py`) reescribe lo segundo para que suene a
persona. Si no hay proveedor, o si lo que devuelve no pasa la
verificación, se publica el determinista. O sea: el LLM es una mejora de
REDACCIÓN sobre un texto que ya era correcto, nunca la fuente de los
hechos. Es la regla §2 de la arquitectura —«el LLM nunca produce
números»— aplicada también a la prosa.

── Lo que NO entra en el resumen ────────────────────────────────
Lo que no se pudo medir. Una lista de métricas suprimidas con su motivo
técnico no le dice nada a quien lee: no puede actuar sobre ella y no
aprende nada de ella. Se cuenta aparte, en una línea (`dropped`), y el
informe la enseña al final y en pequeño. Lo que ocupa el resumen es lo
que SÍ se midió.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .auditor import AuditReport, CrossCheck, Status
from .metrics import REGISTRY

Locale = Literal["es", "en"]

#: Cuántas medidas fuera de rango se nombran en el resumen antes de
#: pasar a contarlas. Tres caben en una frase; siete no las lee nadie.
NAMED_LIMIT = 3

#: Nombre llano de cada métrica del registro. No es el nombre
#: anatómico: es cómo se lo nombrarías a alguien por teléfono.
#:
#: Vive aquí y no en el diccionario del frontend porque el resumen lo
#: redacta el servidor, y un resumen que nombra sus métricas con el
#: identificador interno («nasolabial_angle se sale del rango») es
#: exactamente lo que se está arreglando. Hay un test que comprueba que
#: el registro entero está cubierto en los dos idiomas.
PLAIN_NAMES: dict[str, dict[Locale, str]] = {
    "goode_ratio": {
        "es": "cuánto sobresale la nariz",
        "en": "how far the nose projects",
    },
    "nasolabial_angle": {
        "es": "el ángulo entre la nariz y el labio",
        "en": "the angle between nose and lip",
    },
    "nasofrontal_angle": {
        "es": "el ángulo entre la frente y la nariz",
        "en": "the angle between forehead and nose",
    },
    "facial_convexity_angle": {
        "es": "lo recto o curvado que es el perfil",
        "en": "how straight or curved the profile is",
    },
    "upper_third_pct": {
        "es": "el tercio de arriba de la cara",
        "en": "the upper third of the face",
    },
    "middle_third_pct": {
        "es": "el tercio del medio de la cara",
        "en": "the middle third of the face",
    },
    "lower_third_pct": {
        "es": "el tercio de abajo de la cara",
        "en": "the lower third of the face",
    },
    "mandibular_plane_angle": {
        "es": "la inclinación de la mandíbula",
        "en": "the slope of the jaw",
    },
    "horizontal_fifths": {
        "es": "la separación entre los ojos",
        "en": "the spacing between the eyes",
    },
    "facial_index": {
        "es": "lo alargada o ancha que es la cara",
        "en": "how long or wide the face is",
    },
    "midline_deviation": {
        "es": "la desviación de la línea media",
        "en": "how far off the midline the face strays",
    },
    "canthal_tilt": {
        "es": "la inclinación de los ojos",
        "en": "the tilt of the eyes",
    },
    "nasal_axis_deviation": {
        "es": "la desviación de la nariz",
        "en": "how far the nose deviates",
    },
    "alar_base_symmetry": {
        "es": "la simetría de las aletas de la nariz",
        "en": "the symmetry of the nostrils",
    },
}


def plain_name(metric: str, locale: Locale) -> str:
    """El nombre llano, o el identificador si alguien añadió una métrica
    sin pasar por aquí. Devolver el identificador es feo a propósito: se
    ve en cuanto alguien lo lee, y el test lo caza antes."""
    return PLAIN_NAMES.get(metric, {}).get(locale, metric)


@dataclass(frozen=True, slots=True)
class Measured:
    """Una medida que SÍ se puede publicar."""

    name: str
    value: float
    unit: str
    band: float
    low: float
    high: float
    #: Cae dentro del rango de referencia de la población.
    inside: bool
    #: Se sale por arriba (`high`), por abajo (`low`) o no se sale.
    side: Literal["low", "high", "none"]
    #: Cuánto se sale, en anchos del propio rango de referencia. 0 si
    #: cae dentro. Sirve para ordenar: con seis medidas fuera, el
    #: resumen nombra las que más se salen, no las primeras que pillan.
    off: float = 0.0


@dataclass(frozen=True, slots=True)
class Brief:
    """Los hechos del informe. Es lo único que el agente puede mirar."""

    locale: Locale
    grade: str | None
    measured: tuple[Measured, ...]
    #: Cuántas medidas se quedaron fuera. Sin detalle y a propósito: en
    #: el resumen no pinta nada.
    dropped: int
    agreements: int
    conflicts: int

    @property
    def inside(self) -> tuple[Measured, ...]:
        return tuple(m for m in self.measured if m.inside)

    @property
    def outside(self) -> tuple[Measured, ...]:
        return tuple(m for m in self.measured if not m.inside)

    def numbers(self) -> set[str]:
        """Todas las cifras que el resumen tiene derecho a mencionar.

        La usa el verificador del agente: cualquier número que aparezca
        en su texto y no esté aquí es inventado, y un número inventado en
        este producto no es un error de estilo — es la cosa exacta que la
        portada promete no hacer.
        """
        out: set[str] = {str(len(self.measured)), str(len(self.inside)),
                         str(len(self.outside)), str(self.dropped),
                         str(self.agreements), str(self.conflicts)}
        for m in self.measured:
            for v in (m.value, m.band, m.low, m.high):
                out.add(_num(v))
                out.add(_num(round(v)))
                #: Los ratios se escriben con tres decimales; el agente
                #: puede repetirlos así sin que cuente como inventado.
                out.add(f"{v:.2f}")
                out.add(f"{v:.3f}")
        return out


def _num(value: float) -> str:
    """Un número como lo escribiría el texto: sin ceros de adorno."""
    rounded = round(value, 1)
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:.1f}"


def build_brief(
    reports: dict[str, AuditReport],
    crosses: list[CrossCheck],
    *,
    locale: Locale = "es",
    grade: str | None = None,
) -> Brief:
    """Los hechos, a partir de lo que devolvió el auditor.

    Una métrica medida en las dos vistas de perfil aparece UNA vez: al
    lector le da igual de qué fotografía salió, y verla dos veces con
    dos cifras parecidas sugiere una contradicción donde no la hay. El
    acuerdo entre lados no se pierde — se cuenta en `agreements`, que es
    lo que de verdad significa: esta medida está confirmada por dos
    fotografías distintas.
    """
    seen: dict[str, Measured] = {}
    dropped = 0

    for report in reports.values():
        for m in report.metrics:
            if m.status is not Status.REPORTED or m.value is None:
                dropped += 1
                continue
            if m.name in seen or m.reference is None:
                continue
            low, high = m.reference
            inside = low <= m.value <= high
            width = high - low or 1.0
            off = (
                0.0
                if inside
                else (m.value - high) / width
                if m.value > high
                else (low - m.value) / width
            )
            seen[m.name] = Measured(
                name=m.name,
                value=m.value,
                unit=m.unit,
                band=m.error_band or 0.0,
                low=low,
                high=high,
                inside=inside,
                side="none" if inside else ("low" if m.value < low else "high"),
                off=off,
            )

    #: El orden del informe: primero lo que se sale —que es de lo que
    #: hay algo que decir— y dentro de cada grupo, el registro manda.
    order = {spec.name: i for i, spec in enumerate(REGISTRY)}
    measured = tuple(
        sorted(seen.values(), key=lambda m: (m.inside, order.get(m.name, 99)))
    )

    return Brief(
        locale=locale,
        grade=grade,
        measured=measured,
        dropped=dropped,
        agreements=sum(1 for c in crosses if c.verdict == "concordant"),
        conflicts=sum(1 for c in crosses if c.verdict != "concordant"),
    )


#: Plantillas del resumen determinista. Frases cortas y sin jerga: es el
#: texto que se publica cuando no hay agente, así que tiene que valer
#: por sí solo, no ser un marcador de posición.
_T: dict[Locale, dict[str, str]] = {
    "es": {
        "none": "Todavía no hay ninguna medida que se sostenga. Marca "
                "algún módulo y el informe se llena solo.",
        "one": "Se midió una cosa en tus fotografías.",
        "many": "Se midieron {n} cosas en tus fotografías.",
        "all_inside": " Todas caen dentro de lo habitual.",
        "all_outside": " Ninguna cae dentro de lo habitual.",
        "some": " {n} caen dentro de lo habitual.",
        "one_inside": " Una cae dentro de lo habitual.",
        "out_one": " Se sale {name}, {dir}.",
        "out_many": " Se salen {names}.",
        "out_rest": " Otras {n} también se salen, y las tienes abajo con "
                    "su cifra.",
        "high": "por arriba",
        "low": "por abajo",
        "agree": " Las dos mitades de la cara dan lo mismo, así que esto "
                 "no es cosa de una fotografía suelta.",
        "conflict": " Los dos lados no dan lo mismo: puede ser una "
                    "asimetría real o un fallo al marcar, y hace falta "
                    "repetir el marcado para saber cuál de las dos.",
        "grade_c": " Las fotos salieron justas de calidad, así que estos "
                   "números vienen con más margen del deseable.",
        "close": " Nada de esto es una nota ni un juicio: son "
                 "proporciones, con el margen de error que da tu propio "
                 "marcado.",
    },
    "en": {
        "none": "Nothing measurable yet. Mark one module and the report "
                "fills itself in.",
        "one": "One thing was measured in your photographs.",
        "many": "{n} things were measured in your photographs.",
        "all_inside": " All of them land inside the usual range.",
        "all_outside": " None of them land inside the usual range.",
        "some": " {n} land inside the usual range.",
        "one_inside": " One lands inside the usual range.",
        "out_one": " The one that does not is {name}, {dir}.",
        "out_many": " The ones that do not: {names}.",
        "out_rest": " Another {n} fall outside too, with their figures "
                    "below.",
        "high": "on the high side",
        "low": "on the low side",
        "agree": " Both halves of the face give the same answer, so this "
                 "is not down to a single photograph.",
        "conflict": " The two sides disagree: it can be a real asymmetry "
                    "or a marking slip, and telling them apart needs the "
                    "marking done again.",
        "grade_c": " The photographs came out on the poor side, so these "
                   "numbers carry more margin than one would like.",
        "close": " None of this is a score or a judgement: they are "
                 "proportions, carrying the error margin your own marking "
                 "produced.",
    },
}


def summarize(brief: Brief) -> str:
    """El resumen en prosa, sin LLM y sin red.

    Es el que se publica si no hay agente, así que no es un borrador:
    está escrito para leerse tal cual.
    """
    t = _T[brief.locale]
    if not brief.measured:
        return t["none"]

    n = len(brief.measured)
    parts = [t["one"] if n == 1 else t["many"].format(n=n)]

    inside, outside = brief.inside, brief.outside
    if not outside:
        parts.append(t["all_inside"])
    elif not inside:
        parts.append(t["all_outside"])
    else:
        parts.append(
            t["one_inside"] if len(inside) == 1 else t["some"].format(n=len(inside))
        )

    if len(outside) == 1:
        m = outside[0]
        parts.append(
            t["out_one"].format(name=plain_name(m.name, brief.locale), dir=t[m.side])
        )
    elif outside:
        # Con siete medidas fuera, enumerarlas todas produce una frase
        # que nadie termina. Se nombran las tres que MÁS se salen —por
        # eso `Measured.off`— y el resto se cuenta.
        worst = sorted(outside, key=lambda m: m.off, reverse=True)[:NAMED_LIMIT]
        named = [
            f"{plain_name(m.name, brief.locale)} ({t[m.side]})" for m in worst
        ]
        parts.append(t["out_many"].format(names=_join(named, brief.locale)))
        rest = len(outside) - len(worst)
        if rest:
            parts.append(t["out_rest"].format(n=rest))

    if brief.conflicts:
        parts.append(t["conflict"])
    elif brief.agreements:
        parts.append(t["agree"])

    if brief.grade == "C":
        parts.append(t["grade_c"])

    parts.append(t["close"])
    return "".join(parts)


def _join(items: list[str], locale: Locale) -> str:
    """Enumeración con la conjunción del idioma."""
    if len(items) == 1:
        return items[0]
    last = " y " if locale == "es" else " and "
    return ", ".join(items[:-1]) + last + items[-1]

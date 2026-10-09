"""Los nodos `recommender` y `safety_reviewer`: qué hacer, y qué no.

── El reparto del trabajo ───────────────────────────────────────
Las reglas DECIDEN; el modelo REDACTA. Qué pasos entran, en qué orden,
hasta qué nivel de intervención y a qué precio lo decide este módulo,
con código que se puede leer y testear. El LLM solo escribe una
introducción de dos o tres frases sobre un plan ya cerrado, y esa
introducción pasa por el mismo verificador que el resto del texto.

Es la decisión que hace defendible un sistema que habla de la cara de
alguien y de cirugías: el componente con libertad creativa no tiene
autoridad sobre nada que pueda hacer daño.

── Las reglas, de docs/02 §4 ────────────────────────────────────
1. **Escalera, de menos a más invasivo.** 0 gratis → 1 cosmético → 2
   médico sin cirugía → 3 cirugía. El plan se presenta en ese orden.
2. **Proporcionalidad.** Una medida que se sale poco no abre niveles
   altos (`insight.allowed_level`). Una observación visual, que no tiene
   cifra, nunca pasa del nivel 2; si es solo «probable», del 1.
3. **Primero la piel.** Con piel activa —granos con inflamación—, todo
   lo médico sobre el resto de la cara se POSPONE. Es además requisito
   real: la mayoría de especialistas no pinchan ni operan sobre piel
   inflamada.
4. **Sin certeza no hay recomendación.** Una medida en el borde de su
   margen (`edge`) no genera pasos; la primera recomendación ahí es
   repetir el marcado, y eso ya lo dice su tarjeta.

El `safety_reviewer` vuelve a comprobar 2 y 4 sobre el plan final —
defensa en profundidad: si alguien rompe una regla aguas arriba, el
revisor la para— y además veta cualquier paso con vocabulario de
diagnóstico. Lo que veta se devuelve, con el motivo: un revisor que
retira cosas en silencio es indistinguible de uno que no hace nada.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from .agents import BANNED, _fold, numbers_in, verify
from .insight import allowed_level, certainty
from .knowledge import KNOWLEDGE, Level, Locale, Option
from .narrative import Measured, plain_name
from .observer import DIAGNOSES, TAGS

Country = Literal["ES", "MX", "CO", "AR", "US"]
Confidence = Literal["clear", "probable", "uncertain"]

# ───────────────────── conocimiento de las observaciones ─────────────────────

#: Lo que se puede hacer por cada cosa que el observador VE. Mismo formato
#: y misma escalera que `knowledge.py`; sin nivel 3 en ninguna — una
#: descripción visual sin cifra no justifica nunca una cirugía.
OBSERVATION_OPTIONS: dict[str, tuple[Option, ...]] = {
    "acne_active": (
        Option(0, "No toques ni revientes los granos; limpieza suave dos veces al día y funda de almohada limpia a menudo.",
                  "Do not touch or squeeze spots; gentle cleansing twice a day and a frequently changed pillowcase."),
        Option(1, "Peróxido de benzoilo o adapaleno, sin receta en muchos países: empieza a días alternos, porque al principio irritan.",
                  "Benzoyl peroxide or adapalene, over the counter in many countries: start every other day, as they irritate at first."),
        Option(2, "Si en tres meses no mejora o deja marcas, dermatólogo: hay tratamientos con receta mucho más eficaces.",
                  "If it has not improved in three months or leaves marks, see a dermatologist: prescription treatments are far more effective."),
    ),
    "acne_marks": (
        Option(0, "Protector solar cada día: el sol oscurece las marcas y hace que duren más.",
                  "Sunscreen every day: sun darkens marks and makes them last longer."),
        Option(1, "Niacinamida o un retinoide sin receta aclaran las marcas planas en semanas o meses.",
                  "Niacinamide or an over-the-counter retinoid fades flat marks over weeks or months."),
        Option(2, "Si las marcas son hundidas, dermatólogo: láser o peeling químico.",
                  "If the marks are sunken, see a dermatologist: laser or a chemical peel."),
    ),
    "texture_uneven": (
        Option(0, "Limpieza suave y protector solar: la textura empeora con el sol y con exfoliar de más.",
                  "Gentle cleansing and sunscreen: texture gets worse with sun and over-exfoliation."),
        Option(1, "Un retinoide sin receta, de noche, afina la textura en unos meses.",
                  "An over-the-counter retinoid at night refines texture over a few months."),
        Option(2, "Para poros o cicatrices marcadas, dermatólogo: peeling o láser fraccionado.",
                  "For marked pores or scarring, see a dermatologist: a peel or fractional laser."),
    ),
    "redness": (
        Option(0, "Evita el agua muy caliente, los exfoliantes fuertes y el alcohol sobre la piel; protector solar a diario.",
                  "Avoid very hot water, harsh exfoliants and alcohol on the skin; daily sunscreen."),
        Option(1, "Una crema calmante con niacinamida o centella reduce la rojez de fondo.",
                  "A soothing cream with niacinamide or centella reduces background redness."),
        Option(2, "Si es persistente o va a más, dermatólogo: hay tratamientos con receta y láser vascular.",
                  "If it persists or grows, see a dermatologist: there are prescription treatments and vascular laser."),
    ),
    "dark_circles": (
        Option(0, "Sueño regular y menos sal por la noche reducen la hinchazón. Ojo: parte de la ojera puede ser la sombra de la luz de la foto.",
                  "Regular sleep and less salt at night reduce puffiness. Note: part of the circle may be the shadow of the photo's lighting."),
        Option(1, "Cremas con cafeína o vitamina C aclaran algo; un corrector las disimula al momento.",
                  "Creams with caffeine or vitamin C lighten them a little; a concealer hides them instantly."),
        Option(2, "Si la ojera es un hundimiento y no un color, un relleno en el surco, con un médico con experiencia en esa zona.",
                  "If the circle is a hollow rather than a colour, a filler in the groove, with a doctor experienced in that area."),
    ),
    "pigmentation_spots": (
        Option(0, "Protector solar alto cada día, también nublado: sin él, ninguna otra cosa funciona.",
                  "High-factor sunscreen every day, cloudy days too: without it, nothing else works."),
        Option(1, "Vitamina C o niacinamida por la mañana aclaran las manchas poco a poco.",
                  "Vitamin C or niacinamide in the morning fades spots little by little."),
        Option(2, "Para manchas persistentes, dermatólogo: peeling o láser.",
                  "For persistent spots, see a dermatologist: a peel or laser."),
    ),
    "gum_display_high": (
        Option(0, "Es una variación normal de la sonrisa, no un problema de salud.",
                  "It is a normal variation of the smile, not a health problem."),
        Option(2, "La toxina botulínica en el labio superior reduce la encía visible al sonreír. Temporal: unos meses.",
                  "Botulinum toxin in the upper lip reduces the gum shown when smiling. Temporary: a few months."),
    ),
    "buccal_corridor_wide": (
        Option(0, "Depende sobre todo de la anchura de la arcada dental; es una variación normal.",
                  "It depends mostly on the width of the dental arch; it is a normal variation."),
        Option(2, "Si te importa, un ortodoncista puede valorar ensanchar la arcada.",
                  "If it matters to you, an orthodontist can assess widening the arch."),
    ),
    "smile_arc_flat": (
        Option(0, "Es una variación normal de la sonrisa.",
                  "It is a normal variation of the smile."),
        Option(2, "La forma del arco de los dientes la valora un ortodoncista.",
                  "The shape of the tooth arc is assessed by an orthodontist."),
    ),
    "malar_flat": (
        Option(0, "Un corte de pelo con volumen a los lados de la cara da presencia a la zona del pómulo.",
                  "A haircut with volume at the sides of the face gives presence to the cheekbone area."),
        Option(2, "Un relleno de pómulo añade proyección sin cirugía. Temporal.",
                  "A cheekbone filler adds projection without surgery. Temporary."),
    ),
    "jawline_soft": (
        Option(0, "La postura cuenta: la cabeza adelantada difumina la mandíbula. El peso corporal también la cambia.",
                  "Posture matters: a head pushed forward blurs the jaw. Body weight changes it too."),
        Option(1, "Una barba que siga la línea de la mandíbula la dibuja.",
                  "A beard following the jawline draws it."),
        Option(2, "Un relleno en el ángulo de la mandíbula la define sin cirugía. Temporal.",
                  "A filler at the jaw angle defines it without surgery. Temporary."),
    ),
    "volume_asymmetry": (
        Option(0, "Repite las dos oblicuas con la misma luz y la misma distancia: buena parte de la asimetría aparente es de la toma.",
                  "Retake both obliques with the same light and distance: much of the apparent asymmetry comes from the shot."),
    ),
    "tip_bulbous": (
        Option(0, "No cambia con hábitos. Es de las formas de nariz más comunes.",
                  "No habit changes it. It is one of the most common nose shapes."),
    ),
}

#: Hasta dónde puede llevar una observación visual, según su confianza.
#: Una descripción sin cifra nunca justifica cirugía; si además es solo
#: probable —o salió de una única foto—, tampoco nada médico.
OBSERVATION_MAX_LEVEL: dict[Confidence, int] = {"clear": 2, "probable": 1, "uncertain": -1}

#: Lo que cuenta como piel ACTIVA para la regla «primero la piel».
ACTIVE_SKIN = ("acne_active",)


# ───────────────────────────── precios ─────────────────────────────

CURRENCY: dict[Country, str] = {"ES": "EUR", "MX": "MXN", "CO": "COP", "AR": "USD", "US": "USD"}

#: Rangos ORIENTATIVOS de 2026, redondeados y anchos a propósito: dicen el
#: orden de magnitud, no un presupuesto. Argentina va en dólares porque
#: con su inflación un rango en pesos caduca en semanas. Se publican con
#: esa advertencia al lado, siempre.
PRICES: dict[str, dict[Country, tuple[int, int]]] = {
    "barber":        {"ES": (15, 35), "MX": (150, 450), "CO": (20000, 60000), "AR": (8, 20), "US": (25, 60)},
    "makeup":        {"ES": (10, 30), "MX": (200, 600), "CO": (30000, 90000), "AR": (8, 25), "US": (15, 40)},
    "otc_skincare":  {"ES": (10, 30), "MX": (250, 700), "CO": (40000, 120000), "AR": (10, 30), "US": (15, 40)},
    "hair_loss_otc": {"ES": (15, 35), "MX": (300, 800), "CO": (50000, 140000), "AR": (12, 30), "US": (20, 45)},
    "derm_visit":    {"ES": (60, 130), "MX": (800, 1800), "CO": (150000, 320000), "AR": (30, 70), "US": (150, 300)},
    "ent_visit":     {"ES": (60, 120), "MX": (800, 1700), "CO": (140000, 300000), "AR": (30, 60), "US": (150, 300)},
    "ortho_visit":   {"ES": (40, 90), "MX": (500, 1200), "CO": (80000, 200000), "AR": (25, 60), "US": (100, 250)},
    "derm_procedure": {"ES": (150, 450), "MX": (2500, 7000), "CO": (400000, 1200000), "AR": (100, 300), "US": (300, 900)},
    "filler":        {"ES": (300, 550), "MX": (5000, 9500), "CO": (900000, 1800000), "AR": (200, 400), "US": (700, 1300)},
    "toxin":         {"ES": (250, 400), "MX": (4000, 8000), "CO": (700000, 1500000), "AR": (150, 300), "US": (300, 650)},
    "rhinoplasty":   {"ES": (4000, 7500), "MX": (60000, 130000), "CO": (9000000, 18000000), "AR": (2500, 5500), "US": (7000, 15000)},
    "chin_surgery":  {"ES": (3000, 6000), "MX": (45000, 100000), "CO": (7000000, 14000000), "AR": (2000, 4500), "US": (5000, 10000)},
    "orthognathic":  {"ES": (9000, 18000), "MX": (150000, 300000), "CO": (20000000, 40000000), "AR": (6000, 12000), "US": (20000, 45000)},
    "hair_transplant": {"ES": (3000, 7000), "MX": (50000, 120000), "CO": (8000000, 16000000), "AR": (2000, 4500), "US": (6000, 15000)},
    "eyelid_surgery": {"ES": (2500, 5000), "MX": (40000, 90000), "CO": (6000000, 12000000), "AR": (1800, 4000), "US": (4000, 9000)},
}

#: De qué categoría de precio es cada paso, por palabras de su texto. Se
#: comprueba en los tests que todo paso de nivel 1 o más tiene una.
_COST_RULES: tuple[tuple[str, str], ...] = (
    (r"ortognat|orthognath", "orthognathic"),
    (r"rinoplast|rhinoplast|septorrino|septorhino|septoplast|reseccion alar|alar resection", "rhinoplasty"),
    (r"genioplast|implante de menton|chin implant", "chin_surgery"),
    (r"trasplante|transplant|descenso frontal|hairline-lowering", "hair_transplant"),
    (r"cantopex|canthopex", "eyelid_surgery"),
    (r"relleno|hialur|filler|hyaluron", "filler"),
    (r"toxina|botul|toxin", "toxin"),
    (r"otorrino|\bent\b", "ent_visit"),
    (r"ortodonc|orthodont", "ortho_visit"),
    (r"laser|láser|peeling|peel", "derm_procedure"),
    (r"dermatolog", "derm_visit"),
    (r"caida|hair-loss|hair loss", "hair_loss_otc"),
    (r"maquillaje|make-up|corrector|concealer", "makeup"),
    (r"barba|beard|peinado|corte|haircut|flequillo|fringe", "barber"),
    (r"crema|cream|retinoide|retinoid|niacinamida|niacinamide|vitamina c|vitamin c|"
     r"peroxido|peroxide|adapaleno|adapalene|protector|sunscreen|centella|cafeina|caffeine", "otc_skincare"),
)


def cost_category(text: str) -> str | None:
    folded = _fold(text)
    for pattern, cat in _COST_RULES:
        if re.search(pattern, folded):
            return cat
    return None


# ────────────────────────────── el plan ──────────────────────────────


@dataclass(frozen=True, slots=True)
class ObservationIn:
    tag: str
    confidence: Confidence
    corroborated: bool = False


@dataclass(frozen=True, slots=True)
class Step:
    level: int
    text: str
    #: Qué lo motiva, en lenguaje llano.
    reason: str
    #: `metric:<nombre>` u `observation:<etiqueta>`.
    source: str
    cost: tuple[int, int] | None
    #: Por qué se pospone, si se pospone.
    deferred: str | None = None


@dataclass(frozen=True, slots=True)
class Vetoed:
    text: str
    reason: str
    why: str


@dataclass
class Plan:
    steps: list[Step]
    vetoed: list[Vetoed] = field(default_factory=list)
    currency: str = "EUR"
    intro: str = ""
    intro_source: Literal["agent", "engine"] = "engine"


_T = {
    "es": {
        "skin_first": "Primero la piel: con granos inflamados, casi ningún especialista trata el resto de la cara hasta que se calman.",
        "veto_edge": "la medida está en el borde de su margen: no se puede afirmar que se salga",
        "veto_level": "nivel más alto del que justifica lo encontrado",
        "veto_words": "vocabulario de diagnóstico",
        "intro_none": "No hay nada que proponerte: lo que se midió está dentro de lo habitual y lo que se ve no pide ningún paso.",
        "intro": "Tu plan tiene {n} pasos, ordenados de lo gratis a lo médico. Empieza por los primeros: muchas veces bastan, y ninguno de los siguientes tiene sentido sin haberlos probado.",
        "intro_deferred": " Algunos pasos están pospuestos hasta que la piel esté tranquila.",
    },
    "en": {
        "skin_first": "Skin first: with inflamed spots, almost no specialist treats the rest of the face until they settle.",
        "veto_edge": "the measurement is on the edge of its margin: it cannot be said to be out",
        "veto_level": "a higher level than the finding justifies",
        "veto_words": "diagnostic vocabulary",
        "intro_none": "There is nothing to propose: what was measured is within the usual range and what shows calls for no step.",
        "intro": "Your plan has {n} steps, ordered from free to medical. Start with the first ones: they are often enough, and none of the later ones makes sense without trying them.",
        "intro_deferred": " Some steps are deferred until the skin has calmed down.",
    },
}


def build_plan(
    measured: list[Measured],
    observations: list[ObservationIn],
    *,
    country: Country = "ES",
    locale: Locale = "es",
) -> Plan:
    """El plan, con las reglas aplicadas y el revisor ya pasado."""
    t = _T[locale]
    candidates: list[tuple[Step, dict]] = []

    for m in measured:
        kb = KNOWLEDGE.get(m.name)
        if kb is None or m.inside:
            continue
        cert = certainty(m)
        top = allowed_level(m)
        for o in kb.options[m.side]:  # type: ignore[index]
            if top is not None and o.level <= top and _is_step(o, locale):
                candidates.append((
                    _step(o, plain_name(m.name, locale), f"metric:{m.name}", country, locale),
                    {"certainty": cert, "max": top},
                ))

    for ob in observations:
        tag = TAGS.get(ob.tag)
        if tag is None or not tag.actionable:
            continue
        top = OBSERVATION_MAX_LEVEL[ob.confidence]
        #: Dudosa: no genera ningún paso. Recomendar algo sobre lo que el
        #: propio observador no está seguro de haber visto no es prudente.
        if top < 0:
            continue
        #: Una sola foto: lo más alto que puede proponer es cosmético.
        if not ob.corroborated:
            top = min(top, 1)
        reason = _observation_reason(ob.tag, locale)
        for o in OBSERVATION_OPTIONS.get(ob.tag, ()):
            if not _is_step(o, locale):
                continue
            candidates.append((
                _step(o, reason, f"observation:{ob.tag}", country, locale),
                {"certainty": "firm", "max": top},
            ))

    #: `safety_reviewer`: defensa en profundidad sobre cada candidato.
    steps: list[Step] = []
    vetoed: list[Vetoed] = []
    for step, ctx in candidates:
        why = None
        if ctx["certainty"] == "edge":
            why = t["veto_edge"]
        elif ctx["max"] is None or step.level > ctx["max"]:
            why = t["veto_level"]
        elif any(w.strip() in _fold(step.text) for w in DIAGNOSES):
            why = t["veto_words"]
        if why:
            vetoed.append(Vetoed(step.text, step.reason, why))
        else:
            steps.append(step)

    #: Regla 3: primero la piel.
    active = any(
        o.tag in ACTIVE_SKIN and o.confidence != "uncertain" for o in observations
    )
    if active:
        steps = [
            s if s.level < 2 or s.source.startswith("observation:acne")
            else Step(s.level, s.text, s.reason, s.source, s.cost, t["skin_first"])
            for s in steps
        ]

    #: Regla 1: la escalera. Mismo nivel → primero lo que viene de medir.
    steps.sort(key=lambda s: (s.level, not s.source.startswith("metric:")))
    seen: set[str] = set()
    unique = [s for s in steps if not (s.text in seen or seen.add(s.text))]  # type: ignore[func-returns-value]

    plan = Plan(steps=unique, vetoed=vetoed, currency=CURRENCY[country])
    if not unique:
        plan.intro = t["intro_none"]
    else:
        plan.intro = t["intro"].format(n=len(unique)) + (
            t["intro_deferred"] if any(s.deferred for s in unique) else ""
        )
    return plan


#: Opciones de nivel 0 que no son un PASO sino una constatación —«no
#: cambia con hábitos», «nada que hacer»—. En la tarjeta de la medida
#: tienen sentido: responden a «¿se puede cambiar?». En un plan de cosas
#: que hacer, son una línea que no se puede hacer. Se quedan fuera.
_NOT_A_STEP = re.compile(
    r"^(no cambia con habitos|nada que|no habit|nothing to|es una variacion normal|"
    r"it is a normal variation|depende sobre todo|it depends mostly|no hay nada que corregir|"
    r"nothing to correct)"
)


def _is_step(o: Option, locale: Locale) -> bool:
    return not (o.level == 0 and _NOT_A_STEP.match(_fold(o.text(locale))))


def _step(o: Option, reason: str, source: str, country: Country, locale: Locale) -> Step:
    text = o.text(locale)
    cat = cost_category(text) if o.level >= 1 else None
    return Step(
        level=o.level,
        text=text,
        reason=reason,
        source=source,
        cost=PRICES[cat][country] if cat else None,
    )


_OBS_REASON = {
    "es": {
        "acne_active": "granos activos", "acne_marks": "marcas de granos",
        "texture_uneven": "textura irregular", "redness": "rojez",
        "dark_circles": "ojeras", "pigmentation_spots": "manchas",
        "gum_display_high": "encía visible al sonreír",
        "buccal_corridor_wide": "huecos en las comisuras",
        "smile_arc_flat": "arco de la sonrisa", "malar_flat": "pómulos poco marcados",
        "jawline_soft": "mandíbula difuminada", "volume_asymmetry": "asimetría de volumen",
        "tip_bulbous": "punta de la nariz",
    },
    "en": {
        "acne_active": "active spots", "acne_marks": "acne marks",
        "texture_uneven": "uneven texture", "redness": "redness",
        "dark_circles": "dark circles", "pigmentation_spots": "dark spots",
        "gum_display_high": "gum showing when smiling",
        "buccal_corridor_wide": "gaps at the corners of the smile",
        "smile_arc_flat": "smile arc", "malar_flat": "flat cheekbones",
        "jawline_soft": "soft jawline", "volume_asymmetry": "volume asymmetry",
        "tip_bulbous": "nose tip",
    },
}


def _observation_reason(tag: str, locale: Locale) -> str:
    return _OBS_REASON[locale].get(tag, tag)


# ─────────────────────── la introducción del agente ───────────────────────

INTRO_SYSTEM = {
    "es": (
        "Escribes la introducción de un plan de pasos sobre la cara de alguien. "
        "El plan YA está decidido: no añadas ni quites pasos, no recomiendes "
        "nada, no des precios ni cifras. Explica en 2 o 3 frases, con tuteo y "
        "sin jerga, por qué se empieza por lo gratis y qué conviene mirar "
        "primero. Nada de diagnósticos ni de juicios estéticos. Solo el texto."
    ),
    "en": (
        "You write the introduction to a step plan about someone's face. The "
        "plan is ALREADY decided: do not add or remove steps, do not recommend "
        "anything, give no prices or figures. Explain in 2 or 3 sentences, in "
        "second person and without jargon, why it starts with the free steps "
        "and what is worth looking at first. No diagnoses, no aesthetic "
        "judgements. Text only."
    ),
}


def write_intro(plan: Plan, locale: Locale, provider) -> Plan:  # noqa: ANN001
    """La introducción, redactada por el agente si lo hay y si pasa.

    El texto no puede contener ni una cifra —el plan ya lleva sus
    precios, y un número en la introducción sería un precio inventado—
    ni el vocabulario prohibido de siempre.
    """
    if provider is None or not plan.steps:
        return plan
    facts = "\n".join(
        f"- nivel {s.level}: {s.text} (por: {s.reason}){' [pospuesto]' if s.deferred else ''}"
        for s in plan.steps
    )
    try:
        raw = provider.complete(INTRO_SYSTEM[locale], facts)
    except Exception:  # noqa: BLE001 — cualquier fallo: se queda la plantilla
        return plan
    if verify(raw, set(), max_chars=500) is None and not numbers_in(raw):
        plan.intro = raw.strip()
        plan.intro_source = "agent"
    return plan


__all__ = [
    "BANNED",
    "OBSERVATION_OPTIONS",
    "PRICES",
    "Plan",
    "Step",
    "build_plan",
    "cost_category",
    "write_intro",
]

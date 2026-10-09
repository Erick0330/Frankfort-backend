"""El nodo `visual_observer`: lo que un modelo de visión VE en las fotos.

── Qué hace y por qué existe ────────────────────────────────────
El motor mide geometría: ángulos y proporciones entre puntos marcados.
Hay cosas que prometen las ocho fotos y que la geometría no alcanza: la
piel (granos, marcas, rojeces, ojeras), la sonrisa (cuánta encía se ve,
los huecos oscuros de las comisuras), el volumen (pómulos y mandíbula
vistos en las oblicuas) y la forma de la punta de la nariz desde abajo.
Eso lo describe un modelo de visión.

── Las reglas, que es lo que hace esto defendible ───────────────
Docs/02 §3 fija tres, y aquí se hacen cumplir con código, no con el
prompt:

1. **Nunca produce números.** El modelo describe, el motor mide. Una
   observación con una cifra se descarta entera: una cifra estimada a
   ojo por un modelo, en un producto que publica cada número con su
   banda de error, es una cifra sin banda.
2. **Una sola foto no basta para «claro».** Una observación que solo se
   ve en una fotografía se queda como mucho en «probable». Es la
   generalización del fallo del tercio inferior: lo que sale en una foto
   puede ser la foto.
3. **Vocabulario controlado.** El modelo no inventa categorías: elige una
   etiqueta de `TAGS`, y cada etiqueta dice en qué fotos se puede ver.
   Una observación de la sonrisa sacada de la foto basal se descarta.

Además: nada de diagnósticos con nombre («rosácea», «melasma») —se
describe lo que se ve, no la enfermedad que sugiere— y nada de juicios
estéticos.

── Sin clave ────────────────────────────────────────────────────
Sin proveedor configurado, `observe` devuelve OBSERVACIONES DE EJEMPLO
con `source="example"`, y la pantalla las marca como tales. No son de la
cara de nadie: están para enseñar qué produce esta parte del sistema. Y
pasan por el MISMO verificador que las del modelo — si un ejemplo
rompiera una regla, un test lo cazaría.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from .agents import BANNED, _fold, _post

Locale = Literal["es", "en"]
Area = Literal["skin", "smile", "volume", "nose_tip"]
Confidence = Literal["clear", "probable", "uncertain"]

VIEWS = (
    "frontal_rest",
    "frontal_smile",
    "profile_right",
    "profile_left",
    "oblique_right",
    "oblique_left",
    "basal",
    "skin_closeup",
)


@dataclass(frozen=True, slots=True)
class Tag:
    area: Area
    #: En qué fotos se puede ver esto. Fuera de ellas, se descarta.
    views: tuple[str, ...]
    #: Si es algo sobre lo que el sistema puede ofrecer pasos (`recommender`)
    #: o una observación neutra («piel uniforme»).
    actionable: bool


SKIN_VIEWS = ("skin_closeup", "frontal_rest")
VOLUME_VIEWS = ("oblique_right", "oblique_left")

#: El vocabulario controlado. El modelo elige de aquí; no inventa.
TAGS: dict[str, Tag] = {
    # piel
    "acne_active": Tag("skin", SKIN_VIEWS, True),
    "acne_marks": Tag("skin", SKIN_VIEWS, True),
    "texture_uneven": Tag("skin", SKIN_VIEWS, True),
    "redness": Tag("skin", SKIN_VIEWS, True),
    "dark_circles": Tag("skin", SKIN_VIEWS, True),
    "pigmentation_spots": Tag("skin", SKIN_VIEWS, True),
    "skin_even": Tag("skin", SKIN_VIEWS, False),
    # sonrisa: solo hay una foto que la enseñe
    "gum_display_high": Tag("smile", ("frontal_smile",), True),
    "gum_display_normal": Tag("smile", ("frontal_smile",), False),
    "buccal_corridor_wide": Tag("smile", ("frontal_smile",), True),
    "buccal_corridor_normal": Tag("smile", ("frontal_smile",), False),
    "smile_arc_flat": Tag("smile", ("frontal_smile",), True),
    "smile_arc_consonant": Tag("smile", ("frontal_smile",), False),
    # volumen
    "malar_flat": Tag("volume", VOLUME_VIEWS, True),
    "malar_prominent": Tag("volume", VOLUME_VIEWS, False),
    "jawline_soft": Tag("volume", VOLUME_VIEWS, True),
    "jawline_defined": Tag("volume", VOLUME_VIEWS, False),
    "volume_asymmetry": Tag("volume", VOLUME_VIEWS, True),
    # punta de la nariz, desde abajo
    "tip_bulbous": Tag("nose_tip", ("basal",), True),
    "tip_defined": Tag("nose_tip", ("basal",), False),
}

#: Nombres de enfermedades. Se prohíben en las observaciones: el
#: observador describe lo que se ve («rojez difusa en las mejillas»), no
#: la etiqueta clínica que sugiere («rosácea»). Poner nombre a eso es
#: diagnosticar, y diagnosticar desde una foto de móvil no lo hace ni un
#: dermatólogo.
DIAGNOSES = (
    "rosacea", "melasma", "dermatitis", "psoriasis", "eczema", "lupus",
    "vitiligo", "queratosis", "keratosis", "carcinoma", "melanoma",
    "infeccion", "infection", "hongo", "fungal",
)


@dataclass(frozen=True, slots=True)
class Observation:
    tag: str
    area: Area
    #: La foto de la que sale.
    view: str
    #: Lo que se afirma, en lenguaje llano.
    claim: str
    #: Qué se ve exactamente que lo sostiene.
    evidence: str
    confidence: Confidence
    #: Otras fotos en las que también se ve. Vacío = una sola foto.
    corroborating_views: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ObservationReport:
    observations: list[Observation]
    #: `agent` = lo vio un modelo; `example` = observaciones de ejemplo.
    source: Literal["agent", "example"]
    model: str | None
    #: Por qué se descartó cada observación del modelo. Para el log.
    rejected: list[str]


# ─────────────────────────── las reglas ───────────────────────────


def verify_observation(o: Observation, available: set[str]) -> Observation | str:
    """La observación publicable (quizá rebajada), o el motivo del descarte.

    Rebajar no es lo mismo que descartar. Una observación correcta vista
    en una sola foto no es falsa: es menos segura. Se publica como
    «probable». Una con una cifra o un diagnóstico sí es inaceptable, y
    se tira.
    """
    tag = TAGS.get(o.tag)
    if tag is None:
        return f"etiqueta desconocida: {o.tag!r}"
    if o.area != tag.area:
        return f"{o.tag}: área {o.area!r} no es la suya ({tag.area!r})"
    if o.view not in tag.views:
        return f"{o.tag}: no se puede ver en {o.view!r}"
    if o.view not in available:
        return f"{o.tag}: dice salir de {o.view!r}, y esa foto no se envió"

    for field in (o.claim, o.evidence):
        text = field.strip()
        if not (12 <= len(text) <= 320):
            return f"{o.tag}: texto fuera de longitud"
        if re.search(r"\d", text):
            return f"{o.tag}: trae una cifra — el observador no mide"
        folded = _fold(text)
        for word in BANNED + DIAGNOSES:
            if word.strip() and word.strip() in folded:
                return f"{o.tag}: vocabulario prohibido {word.strip()!r}"

    corroborating = tuple(
        v for v in o.corroborating_views
        if v != o.view and v in tag.views and v in available
    )
    confidence = o.confidence
    if not corroborating and confidence == "clear":
        #: Regla 2: una sola foto nunca es «claro».
        confidence = "probable"
    return replace(o, corroborating_views=corroborating, confidence=confidence)


def verify_all(
    observations: list[Observation], available: set[str]
) -> tuple[list[Observation], list[str]]:
    ok: list[Observation] = []
    rejected: list[str] = []
    seen: set[tuple[str, str]] = set()
    for o in observations:
        out = verify_observation(o, available)
        if isinstance(out, str):
            rejected.append(out)
            continue
        key = (out.tag, out.view)
        if key in seen:
            rejected.append(f"{out.tag}: repetida")
            continue
        seen.add(key)
        ok.append(out)
    return ok, rejected


# ─────────────────────────── el proveedor ───────────────────────────


class VisionProvider(Protocol):
    name: str
    model: str

    def observe(self, system: str, photos: dict[str, bytes], prompt: str) -> str: ...


@dataclass(frozen=True, slots=True)
class GeminiVision:
    """Gemini con imágenes en línea. El único proveedor gratuito con
    visión y cuota suficiente (docs/03). Ver allí también la condición de
    privacidad: la capa gratuita solo es aceptable para caras ajenas si la
    cuenta está en el EEE, Suiza o Reino Unido."""

    key: str
    model: str = "gemini-2.5-flash"
    name: str = "gemini"

    def observe(self, system: str, photos: dict[str, bytes], prompt: str) -> str:
        parts: list[dict] = [{"text": prompt}]
        for view, data in photos.items():
            parts.append({"text": f"Foto: {view}"})
            parts.append(
                {
                    "inlineData": {
                        "mimeType": "image/jpeg",
                        "data": base64.b64encode(data).decode(),
                    }
                }
            )
        out = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent",
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 3000,
                    "responseMimeType": "application/json",
                },
            },
            {"x-goog-api-key": self.key, "Content-Type": "application/json"},
        )
        return out["candidates"][0]["content"]["parts"][0]["text"]


def vision_from_env() -> VisionProvider | None:
    import os

    if os.getenv("FRANKFORT_LLM_PROVIDER", "auto").strip().lower() == "none":
        return None
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    model = os.getenv("FRANKFORT_VISION_MODEL", "").strip()
    return GeminiVision(key=key, **({"model": model} if model else {}))


SYSTEM: dict[Locale, str] = {
    "es": (
        "Eres un observador visual para un informe facial. Describes SOLO lo "
        "que se ve en las fotos, sin medir y sin diagnosticar.\n"
        "Reglas obligatorias:\n"
        "- Ni un solo número, ni siquiera escrito con letras de cantidad exacta.\n"
        "- Nada de nombres de enfermedades: describe lo visible (\"rojez "
        "difusa en las mejillas\"), nunca la etiqueta clínica.\n"
        "- Nada de juicios de belleza.\n"
        "- Cada observación usa UNA etiqueta de esta lista y solo en las fotos "
        "donde esa etiqueta se puede ver: {tags}.\n"
        "- Si lo ves en más de una foto, dilo en corroborating_views.\n"
        "- Confianza: clear (inequívoco), probable, uncertain.\n"
        "- Tuteo, frases cortas. Máximo dos observaciones por zona.\n"
        "Devuelve JSON: {{\"observations\": [{{\"tag\", \"view\", \"claim\", "
        "\"evidence\", \"confidence\", \"corroborating_views\"}}]}}"
    ),
    "en": (
        "You are a visual observer for a facial report. You describe ONLY what "
        "is visible in the photos, without measuring and without diagnosing.\n"
        "Mandatory rules:\n"
        "- Not a single number.\n"
        "- No disease names: describe what is visible (\"diffuse redness on "
        "the cheeks\"), never the clinical label.\n"
        "- No judgements of beauty.\n"
        "- Each observation uses ONE tag from this list, and only on the photos "
        "where that tag can be seen: {tags}.\n"
        "- If you see it in more than one photo, list them in corroborating_views.\n"
        "- Confidence: clear (unambiguous), probable, uncertain.\n"
        "- Second person, short sentences. At most two observations per area.\n"
        "Return JSON: {{\"observations\": [{{\"tag\", \"view\", \"claim\", "
        "\"evidence\", \"confidence\", \"corroborating_views\"}}]}}"
    ),
}


def _tag_catalog() -> str:
    return "; ".join(f"{k} ({'/'.join(t.views)})" for k, t in TAGS.items())


def _parse(raw: str) -> list[Observation]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    data = json.loads(text)
    items = data.get("observations", []) if isinstance(data, dict) else []
    out: list[Observation] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        tag = str(it.get("tag", ""))
        area = TAGS[tag].area if tag in TAGS else "skin"
        conf = it.get("confidence", "uncertain")
        out.append(
            Observation(
                tag=tag,
                area=area,  # type: ignore[arg-type]
                view=str(it.get("view", "")),
                claim=str(it.get("claim", "")),
                evidence=str(it.get("evidence", "")),
                confidence=conf if conf in ("clear", "probable", "uncertain") else "uncertain",  # type: ignore[arg-type]
                corroborating_views=tuple(
                    str(v) for v in it.get("corroborating_views", []) or []
                ),
            )
        )
    return out


def observe(
    photos: dict[str, bytes],
    locale: Locale = "es",
    provider: VisionProvider | None = None,
) -> ObservationReport:
    """Las observaciones de estas fotos, verificadas.

    Sin proveedor —o si el proveedor falla—, las de ejemplo. El informe
    nunca se queda sin esta sección por culpa de un tercero, pero tampoco
    finge: `source` dice siempre qué se está enseñando.
    """
    available = {v for v in photos if v in VIEWS}
    if provider is None:
        obs, rej = verify_all(examples(locale, available), available)
        return ObservationReport(obs, "example", None, rej)

    try:
        raw = provider.observe(
            SYSTEM[locale].format(tags=_tag_catalog()),
            {v: photos[v] for v in sorted(available)},
            "Observa estas fotos." if locale == "es" else "Observe these photos.",
        )
        candidates = _parse(raw)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as exc:
        obs, rej = verify_all(examples(locale, available), available)
        return ObservationReport(obs, "example", None, [f"proveedor: {exc}"] + rej)

    obs, rej = verify_all(candidates, available)
    return ObservationReport(obs, "agent", provider.model, rej)


# ─────────────────────────── los ejemplos ───────────────────────────

_EXAMPLES: dict[Locale, list[Observation]] = {
    "es": [
        Observation(
            "acne_marks", "skin", "skin_closeup",
            "Tienes algunas marcas planas y rojizas en las mejillas, de granos que ya se curaron.",
            "Manchas pequeñas sin relieve ni punta blanca, repartidas por la zona de las mejillas.",
            "clear", ("frontal_rest",),
        ),
        Observation(
            "dark_circles", "skin", "skin_closeup",
            "Debajo de los ojos hay un tono más oscuro que en el resto de la cara.",
            "Una sombra azulada bajo el párpado inferior, igual en los dos ojos.",
            "probable", (),
        ),
        Observation(
            "texture_uneven", "skin", "skin_closeup",
            "La textura de la piel es algo irregular en la nariz y la zona central de la frente.",
            "Poros visibles y un brillo desigual en la zona central de la cara.",
            "uncertain", (),
        ),
        Observation(
            "gum_display_normal", "smile", "frontal_smile",
            "Al sonreír se ve una franja fina de encía por encima de los dientes de arriba.",
            "El labio superior se queda justo en el borde de la encía, sin dejar una banda ancha a la vista.",
            "probable", (),
        ),
        Observation(
            "buccal_corridor_wide", "smile", "frontal_smile",
            "En las comisuras quedan huecos oscuros entre los dientes y las mejillas.",
            "Zonas en sombra a ambos lados de la sonrisa, detrás de los últimos dientes visibles.",
            "uncertain", (),
        ),
        Observation(
            "malar_prominent", "volume", "oblique_right",
            "Tus pómulos se marcan bien al verte en ángulo.",
            "La luz forma un borde nítido sobre el pómulo, con una sombra clara justo debajo.",
            "clear", ("oblique_left",),
        ),
        Observation(
            "jawline_soft", "volume", "oblique_left",
            "La línea de la mandíbula se ve algo difuminada en el tramo cercano a la oreja.",
            "El contorno entre mandíbula y cuello pierde contraste en la parte de atrás.",
            "probable", ("oblique_right",),
        ),
        Observation(
            "tip_defined", "nose_tip", "basal",
            "Desde abajo, la punta de la nariz se ve estrecha y bien definida.",
            "Las dos mitades de la punta se distinguen con claridad y la base no se ensancha.",
            "probable", (),
        ),
    ],
    "en": [
        Observation(
            "acne_marks", "skin", "skin_closeup",
            "You have a few flat, reddish marks on the cheeks from spots that have already healed.",
            "Small marks with no raised area or whitehead, spread over the cheeks.",
            "clear", ("frontal_rest",),
        ),
        Observation(
            "dark_circles", "skin", "skin_closeup",
            "Under the eyes the tone is darker than on the rest of the face.",
            "A bluish shadow under the lower lid, the same on both eyes.",
            "probable", (),
        ),
        Observation(
            "texture_uneven", "skin", "skin_closeup",
            "The skin texture is somewhat uneven on the nose and the middle of the forehead.",
            "Visible pores and uneven shine across the central area of the face.",
            "uncertain", (),
        ),
        Observation(
            "gum_display_normal", "smile", "frontal_smile",
            "When you smile, a thin strip of gum shows above the upper teeth.",
            "The upper lip stops right at the gum line, without leaving a wide band in view.",
            "probable", (),
        ),
        Observation(
            "buccal_corridor_wide", "smile", "frontal_smile",
            "At the corners of the smile there are dark gaps between teeth and cheeks.",
            "Shadowed areas on both sides of the smile, behind the last visible teeth.",
            "uncertain", (),
        ),
        Observation(
            "malar_prominent", "volume", "oblique_right",
            "Your cheekbones show clearly when seen at an angle.",
            "The light draws a sharp edge on the cheekbone, with a clear shadow just below.",
            "clear", ("oblique_left",),
        ),
        Observation(
            "jawline_soft", "volume", "oblique_left",
            "The jawline looks a little blurred in the stretch nearest the ear.",
            "The edge between jaw and neck loses contrast towards the back.",
            "probable", ("oblique_right",),
        ),
        Observation(
            "tip_defined", "nose_tip", "basal",
            "From below, the tip of the nose looks narrow and well defined.",
            "Both halves of the tip are clearly distinguishable and the base does not widen.",
            "probable", (),
        ),
    ],
}


def examples(locale: Locale, available: set[str] | None = None) -> list[Observation]:
    """Las observaciones de ejemplo, solo de las fotos que hay.

    Si no hay foto de la sonrisa, el ejemplo de la sonrisa no sale: un
    ejemplo que habla de una foto que el usuario no hizo enseñaría algo
    que el sistema real nunca produciría.
    """
    items = _EXAMPLES[locale]
    if available is None:
        return list(items)
    return [o for o in items if o.view in available]

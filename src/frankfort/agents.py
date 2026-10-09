"""El agente `explainer`: el único que toca prosa, y con correa corta.

── Qué hace y qué NO hace ───────────────────────────────────────
Recibe los HECHOS (`Brief`) y un resumen ya escrito y correcto, y lo
reescribe para que suene a alguien explicándotelo. No decide nada, no
mide nada y no puede introducir un número que el motor no haya
calculado. Si no hay proveedor configurado, o tarda, o devuelve algo que
no pasa la verificación, se publica el determinista y la respuesta dice
cuál de los dos se usó.

Eso último no es cosmética: un informe que no puede decir de dónde sale
su propio texto es exactamente el producto que esta web dice no ser.

── Por qué la verificación es la parte importante ───────────────
Un LLM redactando sobre medidas faciales inventa dos cosas con enorme
facilidad: cifras («unos 97 grados, ligeramente por encima») y juicios
(«un perfil armónico»). Las dos son inaceptables aquí, la primera porque
contradice al motor y la segunda porque es la puntuación de belleza que
el producto entero existe para no dar.

Así que la salida se comprueba:

  · todo número que aparezca tiene que estar en los hechos;
  · nada de vocabulario de diagnóstico ni de estética;
  · largo acotado, prosa, sin listas ni titulares.

Un fallo de verificación no se arregla ni se reintenta: se descarta. La
alternativa —el texto determinista— ya era publicable.

── Proveedores ──────────────────────────────────────────────────
Groq y Gemini, los dos con capa gratuita (ver docs/03). Se hablan por
HTTP con la biblioteca estándar: una dependencia más en el servidor se
paga en el arranque de un free tier, y esto son dos POST con JSON.

Sin claves configuradas el módulo entero es un no-op. Es el modo por
defecto, y el producto funciona así: la capa de agentes MEJORA el
informe, no lo habilita.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from .insight import Insight
from .narrative import Brief, plain_name, summarize

#: De dónde salió el texto que se publica. Viaja al cliente.
Source = Literal["agent", "engine"]

TIMEOUT_S = 8.0
MAX_CHARS = 800
MIN_CHARS = 40

#: Vocabulario prohibido, sin tildes y en minúsculas (ver `_fold`).
#:
#: Las dos familias tienen motivos distintos. El diagnóstico médico es
#: una promesa que este producto no puede cumplir y una responsabilidad
#: legal que no quiere. El juicio estético es la línea editorial: la
#: portada dice «tu cara no necesita una puntuación», y un resumen que
#: habla de armonía la desmiente en la primera pantalla del informe.
BANNED = (
    "diagnost", "patolog", "enfermedad", "sindrome", "tratamiento",
    "cirugi", "operacion", "quirurg",
    "atractiv", "guapo", "feo", "belleza", "armoni", "estetic",
    "perfecto", "ideal", "puntuacion", "score", "nota ",
    "diagnos", "disease", "surgery", "surgical", "attractive",
    "beauty", "harmoni", "ideal", "flaw",
)


class Provider(Protocol):
    """Lo mínimo que hace falta de un proveedor: texto entra, texto sale."""

    name: str

    def complete(self, system: str, user: str) -> str: ...


@dataclass(frozen=True, slots=True)
class Explanation:
    text: str
    source: Source
    #: Por qué se descartó lo del agente, si se descartó. No viaja al
    #: cliente: se registra en el servidor, que es donde se arregla.
    rejected: str | None = None


def _post(url: str, payload: dict, headers: dict[str, str]) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read().decode())


@dataclass(frozen=True, slots=True)
class Groq:
    """Chat completions compatible con OpenAI."""

    key: str
    model: str = "llama-3.3-70b-versatile"
    name: str = "groq"

    def complete(self, system: str, user: str) -> str:
        data = _post(
            "https://api.groq.com/openai/v1/chat/completions",
            {
                "model": self.model,
                "temperature": 0.3,
                "max_tokens": 400,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            {
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
            },
        )
        return data["choices"][0]["message"]["content"]

    def complete_json(self, system: str, user: str) -> str:
        """Lo mismo, con el modo JSON del proveedor: la salida es JSON
        válido o la llamada falla, en vez de un JSON dentro de prosa que
        luego hay que pescar con expresiones regulares."""
        data = _post(
            "https://api.groq.com/openai/v1/chat/completions",
            {
                "model": self.model,
                "temperature": 0.4,
                "max_tokens": 2400,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            {
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
            },
        )
        return data["choices"][0]["message"]["content"]


@dataclass(frozen=True, slots=True)
class Gemini:
    key: str
    model: str = "gemini-2.5-flash-lite"
    name: str = "gemini"

    def complete(self, system: str, user: str) -> str:
        data = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent",
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 400},
            },
            {"x-goog-api-key": self.key, "Content-Type": "application/json"},
        )
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def complete_json(self, system: str, user: str) -> str:
        data = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent",
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": 0.4,
                    "maxOutputTokens": 2400,
                    "responseMimeType": "application/json",
                },
            },
            {"x-goog-api-key": self.key, "Content-Type": "application/json"},
        )
        return data["candidates"][0]["content"]["parts"][0]["text"]


def provider_from_env() -> Provider | None:
    """El proveedor configurado, o nada.

    `FRANKFORT_LLM_PROVIDER=none` lo apaga aunque haya claves, que es lo
    que se quiere en los tests y en un despliegue que no quiera gastar
    cuota.
    """
    choice = os.getenv("FRANKFORT_LLM_PROVIDER", "auto").strip().lower()
    if choice == "none":
        return None

    model = os.getenv("FRANKFORT_LLM_MODEL", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if choice in ("auto", "groq") and groq_key:
        return Groq(key=groq_key, **({"model": model} if model else {}))
    if choice in ("auto", "gemini") and gemini_key:
        return Gemini(key=gemini_key, **({"model": model} if model else {}))
    return None


SYSTEM = {
    "es": (
        "Reescribes el resumen de un informe de medición facial para que "
        "lo entienda cualquiera. Reglas, todas obligatorias:\n"
        "- Usa SOLO los hechos y las cifras que te doy. No añadas ni un "
        "número más, ni redondees los que hay.\n"
        "- Nada de diagnósticos, dolencias, tratamientos ni cirugía.\n"
        "- Nada de juzgar la cara: ni guapo, ni armónico, ni ideal, ni "
        "puntuaciones.\n"
        "- Tuteo, frases cortas, sin jerga médica y sin adornos.\n"
        "- Prosa seguida: nada de listas, títulos ni negritas.\n"
        "- Entre 3 y 5 frases. Devuelve solo el texto."
    ),
    "en": (
        "You rewrite the summary of a facial measurement report so that "
        "anyone can follow it. All rules are mandatory:\n"
        "- Use ONLY the facts and figures given. Do not add a single "
        "number, and do not round the ones you get.\n"
        "- No diagnoses, conditions, treatments or surgery.\n"
        "- No judging the face: not attractive, not harmonious, not "
        "ideal, no scores.\n"
        "- Short sentences, second person, no medical jargon.\n"
        "- Flowing prose: no lists, headings or bold.\n"
        "- Between 3 and 5 sentences. Return the text only."
    ),
}


def _d(value: float, unit: str) -> str:
    """Los decimales del motor: tres para ratios, uno para lo demás."""
    return f"{value:.3f}" if unit == "ratio" else f"{value:.1f}"


def _facts(brief: Brief) -> str:
    """Los hechos como los ve el agente. Un renglón por medida."""
    lines = [
        f"idioma: {brief.locale}",
        f"medidas publicables: {len(brief.measured)}",
        f"dentro de lo habitual: {len(brief.inside)}",
        f"fuera de lo habitual: {len(brief.outside)}",
        f"confirmadas por los dos lados: {brief.agreements}",
        f"lados que no coinciden: {brief.conflicts}",
        f"calidad de captura: {brief.grade or 'sin declarar'}",
    ]
    for m in brief.measured:
        lines.append(
            f"- {plain_name(m.name, brief.locale)}: {_d(m.value, m.unit)} {m.unit} "
            f"(margen ±{_d(m.band, m.unit)}; lo habitual va de "
            f"{_d(m.low, m.unit)} a {_d(m.high, m.unit)}; "
            f"{'dentro' if m.inside else 'fuera, ' + m.side})"
        )
    return "\n".join(lines)


def _fold(text: str) -> str:
    """Sin tildes y en minúsculas, para comparar vocabulario."""
    stripped = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in stripped if unicodedata.category(c) != "Mn")


NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

#: Palabras que convierten una duda en certeza. Prohibidas SOLO cuando la
#: medida es `edge` —el margen cruza el borde del rango—: ahí el sistema
#: no puede afirmar de qué lado cae, y un «claramente por encima» en la
#: redacción desmentiría el cálculo que se hizo justo para no afirmarlo.
OVERCLAIM = (
    "sin duda", "claramente", "claro que", "definitivamente",
    "seguro que", "evidente",
    "clearly", "definitely", "without doubt", "certainly", "obviously",
)


def numbers_in(text: str) -> set[str]:
    """Las cifras de un texto, normalizadas a punto decimal."""
    return {raw.replace(",", ".") for raw in NUMBER.findall(text)}


def verify(
    text: str,
    allowed: Brief | set[str],
    *,
    min_chars: int = MIN_CHARS,
    max_chars: int = MAX_CHARS,
    hedged: bool = False,
) -> str | None:
    """Devuelve el motivo del rechazo, o None si el texto es publicable.

    `allowed` son las cifras que el texto tiene derecho a mencionar: las
    del resumen (`Brief.numbers`) o, para una explicación, las que venían
    en los hechos que se le dieron al agente. Un número que no esté ahí
    es inventado, y se tumba el texto entero.

    `hedged` activa la guarda de sobreafirmación de las medidas `edge`.
    """
    clean = text.strip()
    if len(clean) < min_chars:
        return "demasiado corto"
    if len(clean) > max_chars:
        return "demasiado largo"
    if re.search(r"^\s*[-*#>]|\*\*", clean, re.MULTILINE):
        return "trae listas o marcado"

    folded = _fold(clean)
    for word in BANNED:
        if word in folded:
            return f"vocabulario prohibido: {word!r}"
    if hedged:
        for word in OVERCLAIM:
            if word in folded:
                return f"afirma lo que el margen no permite: {word!r}"

    ok = allowed.numbers() if isinstance(allowed, Brief) else allowed
    for raw in numbers_in(clean):
        if raw not in ok:
            return f"número inventado: {raw}"
    return None


def explain(
    brief: Brief,
    provider: Provider | None = None,
) -> Explanation:
    """El resumen que se publica, y de dónde salió.

    Nunca lanza: un informe no se cae porque un proveedor gratuito tenga
    un mal día. Cualquier fallo —red, cuota, JSON raro, verificación— se
    resuelve publicando el texto del motor.
    """
    fallback = summarize(brief)
    if provider is None or not brief.measured:
        return Explanation(text=fallback, source="engine")

    try:
        raw = provider.complete(
            SYSTEM[brief.locale],
            f"{_facts(brief)}\n\n"
            f"Resumen del motor, para reescribir:\n{fallback}",
        )
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as exc:
        return Explanation(
            text=fallback, source="engine", rejected=f"{type(exc).__name__}: {exc}"
        )

    bad = verify(raw, brief)
    if bad is not None:
        return Explanation(text=fallback, source="engine", rejected=bad)
    return Explanation(text=raw.strip(), source="agent")


# ───────────────────────── personalización ─────────────────────────

PERSONALIZE_SYSTEM = {
    "es": (
        "Eres el redactor de un informe de medición facial. Para cada medida "
        "te doy los HECHOS ya calculados y una redacción base correcta. Tu "
        "trabajo es reescribir dos campos para ESA persona concreta:\n"
        "- reading: cómo está su medida. Di la cifra, dónde cae respecto a lo "
        "habitual y cuánta confianza hay según su margen. Si la certeza es "
        "'edge', deja claro que el margen no permite afirmarlo. 2 o 3 frases.\n"
        "- meaning: qué quiere decir eso en lo que se ve de su cara. Puedes "
        "relacionarla con sus OTRAS medidas si eso ayuda a entenderla (por "
        "ejemplo, un tercio largo va con otro corto). 1 a 3 frases.\n"
        "Reglas obligatorias:\n"
        "- Usa SOLO las cifras que aparecen en los hechos, escritas igual.\n"
        "- Nada de consejos, tratamientos, cirugía ni diagnósticos: las "
        "opciones de cambio las pone otra parte del sistema.\n"
        "- Nada de juzgar la cara: ni guapo, ni armónico, ni ideal.\n"
        "- Tuteo, lenguaje llano, sin jerga, prosa sin listas.\n"
        'Devuelve JSON: {"metrics": {"<id>": {"reading": "...", "meaning": "..."}}}'
    ),
    "en": (
        "You write a facial measurement report. For each measurement you get "
        "the FACTS, already computed, and a correct base wording. Your job is "
        "to rewrite two fields for THIS specific person:\n"
        "- reading: how their measurement stands. State the figure, where it "
        "falls against the usual range and how much confidence its margin "
        "allows. If certainty is 'edge', make clear the margin cannot settle "
        "it. 2 or 3 sentences.\n"
        "- meaning: what that means for how their face looks. You may relate "
        "it to their OTHER measurements if that helps (for instance, one long "
        "third goes with a short one). 1 to 3 sentences.\n"
        "Mandatory rules:\n"
        "- Use ONLY figures that appear in the facts, written the same way.\n"
        "- No advice, treatments, surgery or diagnoses: options for change "
        "come from another part of the system.\n"
        "- No judging the face: not attractive, not harmonious, not ideal.\n"
        "- Second person, plain language, no jargon, prose without lists.\n"
        'Return JSON: {"metrics": {"<id>": {"reading": "...", "meaning": "..."}}}'
    ),
}


def _insight_facts(insights: list[Insight], brief: Brief) -> dict:
    """Lo que ve el agente: los hechos de TODAS las medidas a la vez.

    Una sola llamada para todas, no una por medida, y por dos motivos. El
    presupuesto: con la cuota gratuita de Groq (docs/03), ocho llamadas por
    informe son la mitad de los informes que caben en un día. Y la
    calidad: el agente solo puede decir «tu tercio del medio es largo, y
    por eso el de abajo sale corto» si ve los dos a la vez.
    """
    by_name = {m.name: m for m in brief.measured}
    return {
        "locale": brief.locale,
        "capture_quality": brief.grade or "unknown",
        "metrics": {
            i.name: {
                "name": plain_name(i.name, brief.locale),
                "what_it_measures": i.what,
                "position": i.position,
                "certainty": i.certainty,
                "unit": by_name[i.name].unit,
                "base_reading": i.reading,
                "base_meaning": i.meaning,
            }
            for i in insights
        },
    }


def _parse_json(raw: str) -> dict:
    """JSON del proveedor, tolerando la valla de markdown que algunos
    modelos ponen aunque se les pida JSON puro."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("la respuesta no es un objeto")
    return data


@dataclass(frozen=True, slots=True)
class Personalized:
    insights: list[Insight]
    #: Motivo de cada campo descartado, por métrica. Solo para el log.
    rejected: dict[str, str]


def personalize(
    insights: list[Insight],
    brief: Brief,
    provider: Provider | None = None,
) -> Personalized:
    """Reescribe `reading` y `meaning` de cada medida para esa persona.

    ── Lo que el agente NO toca ─────────────────────────────────────
    `what` (qué es la medida) y las `options` (qué se puede hacer). El
    primero es conocimiento y no mejora personalizándolo. Las segundas son
    la parte con riesgo real —recomendar algo sobre la cara de alguien—, y
    por eso las elige una regla de proporcionalidad y las redacta un
    humano en `knowledge.py`. El LLM redacta; no decide.

    ── Verificación campo a campo ───────────────────────────────────
    Cada campo de cada medida se verifica por separado, y el que falla se
    sustituye por el del motor sin tirar el resto. Un número inventado en
    la explicación de la mandíbula no es motivo para perder la de la nariz.
    """
    if provider is None or not insights:
        return Personalized(insights, {})

    complete = getattr(provider, "complete_json", None) or provider.complete
    facts_text = json.dumps(_insight_facts(insights, brief), ensure_ascii=False)
    #: El agente solo puede repetir cifras que ha visto.
    allowed = numbers_in(facts_text)

    try:
        data = _parse_json(complete(PERSONALIZE_SYSTEM[brief.locale], facts_text))
        data = data.get("metrics", {})
        if not isinstance(data, dict):
            raise ValueError("'metrics' no es un objeto")
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as exc:
        return Personalized(insights, {"*": f"{type(exc).__name__}: {exc}"})

    out: list[Insight] = []
    rejected: dict[str, str] = {}
    for ins in insights:
        entry = data.get(ins.name)
        if not isinstance(entry, dict):
            rejected[ins.name] = "sin respuesta"
            out.append(ins)
            continue

        fields: dict[str, str] = {}
        for key, limit in (("reading", 520), ("meaning", 420)):
            text = entry.get(key)
            if not isinstance(text, str):
                rejected[f"{ins.name}.{key}"] = "falta"
                continue
            bad = verify(
                text,
                allowed,
                min_chars=20,
                max_chars=limit,
                hedged=ins.certainty == "edge",
            )
            if bad:
                rejected[f"{ins.name}.{key}"] = bad
            else:
                fields[key] = text.strip()

        out.append(replace(ins, **fields, source="agent") if fields else ins)
    return Personalized(out, rejected)

"""Banco de evaluación del observador visual.

Pasa el observador por las ocho fotos de prueba y puntúa cuánto respeta
las reglas — no cuánto acierta: para medir aciertos haría falta un
conjunto anotado por un especialista, y no lo hay. Lo que sí se puede
medir sin él, y es lo que más importa en producción:

  · **Cumplimiento**: qué fracción de lo que devuelve el modelo pasa el
    verificador (sin cifras, sin diagnósticos, etiqueta y foto válidas).
  · **Rebajas**: cuántas veces dijo «claro» con una sola foto y hubo que
    bajarlo a «probable». Mide lo sobreconfiado que es el modelo.
  · **Cobertura**: de las cuatro zonas que la foto permite ver, de
    cuántas dijo algo.
  · **Latencia** de la llamada.

Uso, desde `api/`:

    GEMINI_API_KEY=... uv run python scripts/eval_observer.py
    uv run python scripts/eval_observer.py            # sin clave: ejemplos

Sin clave corre sobre las observaciones de ejemplo, y lo dice en la
primera línea: sirve para comprobar que el banco funciona, no para
puntuar ningún modelo.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from frankfort.observer import (  # noqa: E402
    TAGS,
    _parse,
    examples,
    verify_observation,
    vision_from_env,
    SYSTEM,
    _tag_catalog,
)

PHOTOS = Path(__file__).resolve().parents[2] / "web" / "public" / "frames" / "tests"
#: El orden en que la app pide las fotos, y el que tienen los ficheros.
ORDER = (
    "frontal_rest", "frontal_smile", "profile_right", "profile_left",
    "oblique_right", "oblique_left", "basal", "skin_closeup",
)


def main(locale: str = "es") -> int:
    photos = {
        view: (PHOTOS / f"{i}.jpg").read_bytes()
        for i, view in enumerate(ORDER, start=1)
        if (PHOTOS / f"{i}.jpg").exists()
    }
    if not photos:
        print(f"No hay fotos de prueba en {PHOTOS}")
        return 1
    available = set(photos)

    provider = vision_from_env()
    t0 = time.perf_counter()
    if provider is None:
        print("SIN CLAVE — se evalúan las observaciones de EJEMPLO, no un modelo.")
        candidates = examples(locale, available)  # type: ignore[arg-type]
        label = "ejemplos"
    else:
        raw = provider.observe(
            SYSTEM[locale].format(tags=_tag_catalog()),  # type: ignore[index]
            photos,
            "Observa estas fotos." if locale == "es" else "Observe these photos.",
        )
        candidates = _parse(raw)
        label = f"{provider.name}/{provider.model}"
    elapsed = time.perf_counter() - t0

    passed, downgraded, reasons = 0, 0, []
    areas_seen: set[str] = set()
    for c in candidates:
        out = verify_observation(c, available)
        if isinstance(out, str):
            reasons.append(out)
            continue
        passed += 1
        areas_seen.add(out.area)
        if c.confidence == "clear" and out.confidence != "clear":
            downgraded += 1

    possible = {t.area for t in TAGS.values() if set(t.views) & available}
    total = len(candidates)
    print(f"Fuente: {label} · fotos: {len(photos)} · latencia: {elapsed:.2f} s")
    print(f"Cumplimiento: {passed}/{total} ({100 * passed / max(total, 1):.0f} %)")
    print(f"Rebajadas de «claro» a «probable» (una sola foto): {downgraded}")
    print(f"Cobertura de zonas: {len(areas_seen)}/{len(possible)} {sorted(areas_seen)}")
    for r in reasons:
        print(f"  descartada: {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*(sys.argv[1:2] or ["es"])))

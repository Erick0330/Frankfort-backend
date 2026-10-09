"""Caras sintéticas de geometría conocida.

Cada fixture está construida para que la respuesta correcta sea un número
exacto y calculable a mano, no "aproximadamente lo que salga". Si un
refactor rompe el motor, estos tests lo dicen con precisión.

Fixtures separadas por grupo de métricas en vez de una cara completa: una
cara anatómicamente plausible NO tiene tercios exactos ni un Goode
redondo a la vez, y forzarlo daría una fixture mentirosa.
"""

from __future__ import annotations

import numpy as np
import pytest

from frankfort.landmarks import Point
from frankfort.reliability import MarkedPoint, MarkingSet


def p(x: float, y: float) -> np.ndarray:
    return np.array([x, y], dtype=np.float64)


def single(point: Point, x: float, y: float) -> MarkedPoint:
    return MarkedPoint(point=point, passes=(p(x, y),))


def double(
    point: Point, a: tuple[float, float], b: tuple[float, float]
) -> MarkedPoint:
    return MarkedPoint(point=point, passes=(p(*a), p(*b)))


#: Plano de Frankfort horizontal, longitud 60. Es la escala de referencia
#: en las vistas de perfil (no hay distancia intercantal ahí).
FRANKFORT_SCALE = 60.0


def frankfort_points(tilt_deg: float = 0.0) -> dict[Point, MarkedPoint]:
    """Porion y orbitale, opcionalmente inclinados para probar la alineación."""
    porion = p(10.0, 45.0)
    if tilt_deg == 0.0:
        orbitale = p(70.0, 45.0)
    else:
        t = np.radians(tilt_deg)
        # rotación en pantalla: y invertida
        d = np.array([np.cos(t), -np.sin(t)]) * FRANKFORT_SCALE
        orbitale = porion + d
    return {
        Point.PORION: MarkedPoint(Point.PORION, (porion,)),
        Point.ORBITALE: MarkedPoint(Point.ORBITALE, (orbitale,)),
    }


@pytest.fixture
def thirds_marking() -> MarkingSet:
    """Tercios verticales EXACTAMENTE iguales: 33,333 % cada uno.

    trichion y=0, glabella y=30, subnasale y=60, menton y=90.
    Altura total 90, cada tercio 30.

    Los cuatro son puntos frágiles, así que van con doble marcado y
    discrepancia pequeña (1.0 sobre escala 60 = 1,7 %, por debajo de la
    tolerancia del 6 %) para que salgan fiables.
    """
    pts: dict[Point, MarkedPoint] = {
        Point.TRICHION: double(Point.TRICHION, (50.0, -0.5), (50.0, 0.5)),
        Point.GLABELLA: double(Point.GLABELLA, (50.0, 29.5), (50.0, 30.5)),
        Point.SUBNASALE: double(Point.SUBNASALE, (50.0, 59.5), (50.0, 60.5)),
        Point.MENTON: double(Point.MENTON, (50.0, 89.5), (50.0, 90.5)),
    }
    pts.update(frankfort_points())
    return MarkingSet(points=pts, scale=FRANKFORT_SCALE, capture_grade="A")


@pytest.fixture
def thirds_marking_bad_subnasale() -> MarkingSet:
    """Igual, pero Subnasale marcado dos veces con 6 unidades de diferencia.

    6 / 60 = 10 %, por encima de la tolerancia del 6 % → punto NO fiable.

    Es el caso real que cuenta la landing: el tercio superior no depende
    de Subnasale y debe sobrevivir; el medio y el inferior sí y deben
    caer. Uno de tres.
    """
    pts: dict[Point, MarkedPoint] = {
        Point.TRICHION: double(Point.TRICHION, (50.0, -0.5), (50.0, 0.5)),
        Point.GLABELLA: double(Point.GLABELLA, (50.0, 29.5), (50.0, 30.5)),
        Point.SUBNASALE: double(Point.SUBNASALE, (50.0, 57.0), (50.0, 63.0)),
        Point.MENTON: double(Point.MENTON, (50.0, 89.5), (50.0, 90.5)),
    }
    pts.update(frankfort_points())
    return MarkingSet(points=pts, scale=FRANKFORT_SCALE, capture_grade="A")


@pytest.fixture
def nasal_marking() -> MarkingSet:
    """Perfil nasal con Goode = 0,575 y nasolabial = 90° exactos.

    Goode: dorso nasion(52,40) → pronasale(76,72) = √(24²+32²) = 40
           proyección alar_crease(53,74) → pronasale x = |76−53| = 23
           23 / 40 = 0,575  ← centro del rango de referencia (0,55–0,60)

    Nasolabial: en subnasale(50,60), rayos a columella_apex(60,50) y a
    labrale_superius(40,50). Los vectores (10,−10) y (−10,−10) tienen
    producto escalar 0 → exactamente 90°.
    """
    pts: dict[Point, MarkedPoint] = {
        Point.NASION: double(Point.NASION, (52.0, 39.5), (52.0, 40.5)),
        Point.PRONASALE: double(Point.PRONASALE, (75.5, 72.0), (76.5, 72.0)),
        Point.ALAR_CREASE: double(Point.ALAR_CREASE, (52.5, 74.0), (53.5, 74.0)),
        Point.SUBNASALE: double(Point.SUBNASALE, (49.5, 60.0), (50.5, 60.0)),
        Point.COLUMELLA_APEX: single(Point.COLUMELLA_APEX, 60.0, 50.0),
        Point.LABRALE_SUPERIUS: single(Point.LABRALE_SUPERIUS, 40.0, 50.0),
        Point.GLABELLA: double(Point.GLABELLA, (50.0, 19.5), (50.0, 20.5)),
        Point.POGONION: double(Point.POGONION, (54.0, 99.5), (54.0, 100.5)),
    }
    pts.update(frankfort_points())
    return MarkingSet(points=pts, scale=FRANKFORT_SCALE, capture_grade="A")


@pytest.fixture
def mandible_marking() -> MarkingSet:
    """Plano mandibular con inclinación conocida.

    gonion_r(30,80) → menton(70,100): dx = 40, dy en pantalla = +20, así
    que la inclinación es atan2(−20, 40) = −26,565°, y en valor absoluto
    26,565° — dentro del rango de referencia (22–28).
    """
    pts: dict[Point, MarkedPoint] = {
        Point.GONION_R: single(Point.GONION_R, 30.0, 80.0),
        Point.MENTON: double(Point.MENTON, (70.0, 99.8), (70.0, 100.2)),
    }
    pts.update(frankfort_points())
    return MarkingSet(points=pts, scale=FRANKFORT_SCALE, capture_grade="A")

"""Las cuatro medidas frontales, contra una cara de geometría conocida.

Mismo método que el resto del motor: se construye una cara sintética
cuyas medidas se saben de antemano —calculadas a mano, no con el código
que se prueba— y se comprueba que el motor las devuelve. Y después se
gira la cara entera, porque la promesa de medir contra la línea
intercantal es justo esa: que una cabeza ladeada en la foto no mueva
ninguna cifra.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from frankfort.geometry import rotate
from frankfort.landmarks import Point
from frankfort.metrics import BY_NAME

TILT = 5.0
EYE = 30.0


def face() -> dict[Point, np.ndarray]:
    """Cara de frente, con valores elegidos para que salgan redondos.

    · intercantal 30 y ojos de 30 → quintos = 1,0
    · esquinas externas subidas 5° → inclinación = 5°
    · altura nasion→gnathion 88, anchura cigomática 100 → índice = 88
    · subnasale 3 px fuera de la línea media sobre 30 → desvío = 10 %
    """
    up = EYE * math.sin(math.radians(TILT))
    out = EYE * math.cos(math.radians(TILT))
    pts = {
        Point.ENDOCANTHION_R: (-15.0, 0.0),
        Point.ENDOCANTHION_L: (15.0, 0.0),
        # `y` crece hacia abajo: subir es restar.
        Point.EXOCANTHION_R: (-15.0 - out, -up),
        Point.EXOCANTHION_L: (15.0 + out, -up),
        Point.ZYGION_R: (-50.0, 20.0),
        Point.ZYGION_L: (50.0, 20.0),
        Point.NASION: (0.0, -2.0),
        Point.GNATHION: (0.0, 86.0),
        Point.SUBNASALE: (3.0, 40.0),
        Point.MENTON: (1.5, 90.0),
    }
    return {k: np.array(v, dtype=np.float64) for k, v in pts.items()}


def turned(points: dict[Point, np.ndarray], degrees: float) -> dict[Point, np.ndarray]:
    """La misma cara, girada en el plano de la foto y desplazada."""
    rot = rotate({k.value: v for k, v in points.items()}, degrees, about=np.zeros(2))
    return {Point(k): v + np.array([400.0, 300.0]) for k, v in rot.items()}


EXPECTED = {
    "horizontal_fifths": 1.0,
    "canthal_tilt": TILT,
    "facial_index": 88.0,
    "midline_deviation": 10.0,
}


@pytest.mark.parametrize("name,value", EXPECTED.items())
def test_cada_frontal_da_su_valor_conocido(name: str, value: float):
    assert BY_NAME[name].evaluate(face()) == pytest.approx(value, abs=1e-6)


@pytest.mark.parametrize("degrees", [-12.0, 7.0, 20.0])
@pytest.mark.parametrize("name,value", EXPECTED.items())
def test_una_cabeza_ladeada_no_cambia_ninguna_cifra(name, value, degrees):
    """Es la razón de medir contra la línea intercantal y no contra el
    borde de la foto. Si esto fallara, la inclinación de los ojos de
    alguien dependería de cómo sujetó el móvil."""
    assert BY_NAME[name].evaluate(turned(face(), degrees)) == pytest.approx(
        value, abs=1e-6
    )


def test_la_inclinacion_tiene_signo():
    """Esquina externa por DEBAJO de la interna = negativo. Es la mitad
    del dato: «caída hacia fuera» y «rasgada hacia arriba» son opuestos."""
    p = face()
    for side in (Point.EXOCANTHION_R, Point.EXOCANTHION_L):
        p[side] = p[side] * np.array([1.0, -1.0])  # refleja verticalmente
    assert BY_NAME["canthal_tilt"].evaluate(p) == pytest.approx(-TILT, abs=1e-6)


def test_el_desvio_es_el_mayor_de_los_dos():
    p = face()
    p[Point.MENTON] = np.array([-6.0, 90.0])  # 6/30 = 20 %, más que la nariz
    assert BY_NAME["midline_deviation"].evaluate(p) == pytest.approx(20.0)


def test_el_tamano_de_la_foto_no_importa():
    """Ratios y ángulos: escalar la cara entera no mueve nada."""
    big = {k: v * 3.7 for k, v in face().items()}
    for name, value in EXPECTED.items():
        assert BY_NAME[name].evaluate(big) == pytest.approx(value, abs=1e-6)


def test_ninguna_frontal_necesita_frankfort():
    """Porion y orbitale no se ven de frente. Si alguna frontal pidiera
    Frankfort, saldría siempre «no calculable» — que es exactamente lo
    que les pasa a los tercios en esta vista."""
    for name in EXPECTED:
        assert BY_NAME[name].needs_frankfort is False


def test_los_puntos_que_faltan_se_dicen():
    p = face()
    del p[Point.ZYGION_L]
    from frankfort.metrics import MissingPoints

    with pytest.raises(MissingPoints):
        BY_NAME["facial_index"].evaluate(p)

"""Las dos medidas de la basal, contra una nariz de geometría conocida.

Mismo método que las frontales: valores calculados a mano, y después la
nariz girada en el plano de la foto, porque desde abajo es imposible
sostener el móvil perfectamente recto y la medida no puede depender de
eso.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from frankfort.geometry import rotate
from frankfort.landmarks import Point, View
from frankfort.metrics import BY_NAME
from frankfort.reliability import scale_pair_for

DEV = 6.0


def nose(dev: float = DEV, right: float = 18.0, left: float = 22.0) -> dict[Point, np.ndarray]:
    """Base nasal vista desde abajo.

    · aletas en (-20, 0) y (20, 0): línea de aletas horizontal;
    · columela de (0, 0) a la punta, inclinada `dev` grados;
    · la aleta derecha a `right` del eje y la izquierda a `left`.
    """
    t = math.radians(dev)
    tip = np.array([30.0 * math.sin(t), -30.0 * math.cos(t)])
    base = np.array([0.0, 0.0])
    axis = (tip - base) / np.linalg.norm(tip - base)
    normal = np.array([-axis[1], axis[0]])  # hacia la izquierda del sujeto
    # Las aletas se sitúan a la distancia pedida del eje, sobre la base.
    return {
        Point.SUBNASALE: base,
        Point.PRONASALE: tip,
        Point.ALARE_R: base - normal * right,
        Point.ALARE_L: base + normal * left,
    }


def expected_symmetry(right: float, left: float) -> float:
    return 100.0 * abs(right - left) / (right + left)


def test_la_desviacion_da_su_angulo():
    """Las aletas se colocan perpendiculares al eje desviado, así que la
    línea de aletas gira con él y el desvío RELATIVO es cero: la nariz
    entera está girada, no torcida. Es la foto ladeada, no la cara."""
    assert BY_NAME["nasal_axis_deviation"].evaluate(nose()) == pytest.approx(0.0, abs=1e-6)


def test_una_columela_torcida_respecto_a_las_aletas_si_se_mide():
    p = nose(dev=0.0)
    # Se tuerce SOLO la punta: ahora sí hay desviación respecto a la base.
    t = math.radians(DEV)
    p[Point.PRONASALE] = np.array([30.0 * math.sin(t), -30.0 * math.cos(t)])
    assert BY_NAME["nasal_axis_deviation"].evaluate(p) == pytest.approx(DEV, abs=1e-6)


def test_la_simetria_da_su_porcentaje():
    assert BY_NAME["alar_base_symmetry"].evaluate(nose()) == pytest.approx(
        expected_symmetry(18.0, 22.0), abs=1e-6
    )


def test_base_perfectamente_simetrica_da_cero():
    assert BY_NAME["alar_base_symmetry"].evaluate(nose(right=20, left=20)) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("degrees", [-15.0, 9.0, 30.0])
def test_girar_la_foto_no_cambia_nada(degrees):
    """Desde abajo nadie sujeta el móvil recto."""
    p = nose(dev=0.0)
    t = math.radians(DEV)
    p[Point.PRONASALE] = np.array([30.0 * math.sin(t), -30.0 * math.cos(t)])
    rot = rotate({k.value: v for k, v in p.items()}, degrees, about=np.zeros(2))
    q = {Point(k): v + 50.0 for k, v in rot.items()}
    assert BY_NAME["nasal_axis_deviation"].evaluate(q) == pytest.approx(DEV, abs=1e-6)
    assert BY_NAME["alar_base_symmetry"].evaluate(q) == pytest.approx(
        BY_NAME["alar_base_symmetry"].evaluate(p), abs=1e-6
    )


def test_la_basal_tiene_su_propia_escala():
    """Desde abajo los ojos se ven escorzados o tapados: pedir la
    intercantal ahí obligaba a marcar puntos que no se ven bien."""
    assert set(scale_pair_for(View.BASAL)) == {Point.ALARE_L, Point.ALARE_R}


def test_ninguna_basal_necesita_frankfort():
    for name in ("nasal_axis_deviation", "alar_base_symmetry"):
        assert BY_NAME[name].needs_frankfort is False
        assert BY_NAME[name].views == (View.BASAL,)

"""Fiabilidad del marcado y propagación de error a las métricas.

Aquí está la diferencia entre reportar "95°" y reportar "95° ± 3°". La
banda no se inventa ni se hardcodea: sale de cuánto se movió cada punto
entre las dos pasadas de marcado, propagado a la métrica por muestreo.

Todo determinista: misma entrada y misma semilla, mismo resultado. Es
requisito para que sea testeable y para que un informe sea reproducible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from .geometry import Vec, as_point, distance
from .landmarks import FRAGILE_POINTS, Point, View, is_profile
from .metrics import MetricSpec, PointMap

CaptureGrade = Literal["A", "B", "C"]

#: Cuánto se ensancha la incertidumbre según la calidad de la captura.
#: C es el caso del selfie a distancia de brazo con gran angular: la
#: distorsión de perspectiva no se puede corregir sin conocer la focal,
#: así que se paga en anchura de banda.
GRADE_FACTOR: dict[CaptureGrade, float] = {"A": 1.0, "B": 1.5, "C": 2.5}

#: Incertidumbre mínima de un punto marcado una sola vez, como fracción
#: de la distancia de referencia. Un punto automático de MediaPipe no
#: tiene dispersión observada, pero tampoco es exacto.
SINGLE_MARK_SIGMA: float = 0.015

#: Un punto frágil cuyas dos marcas discrepen más que esto (fracción de
#: la distancia de referencia) se declara NO FIABLE, y arrastra consigo
#: todas las métricas que dependen de él.
DEFAULT_TOLERANCE: float = 0.06


#: La pareja de puntos que define la distancia de referencia de cada
#: tipo de vista. Ver `MarkingSet.scale`.
#:
#: Está aquí y no en la capa HTTP porque es una regla de medición, no de
#: transporte: decide contra qué se compara cada discrepancia. El
#: frontend tiene su espejo en `web/src/lib/landmarks.ts` (SCALE_PAIR),
#: porque necesita juzgar el doble marcado en el momento, sin red.
SCALE_PAIR: dict[str, tuple[Point, Point]] = {
    "frontal": (Point.ENDOCANTHION_L, Point.ENDOCANTHION_R),
    "profile": (Point.PORION, Point.ORBITALE),
    #: En la basal —la cara vista desde abajo— los ojos quedan escorzados
    #: o directamente tapados por las mejillas, así que la intercantal no
    #: sirve. La anchura de las aletas de la nariz sí: dos bordes nítidos
    #: y siempre en el encuadre de esta vista.
    "basal": (Point.ALARE_L, Point.ALARE_R),
}


class MissingScalePoints(ValueError):
    """Falta la pareja que define la distancia de referencia."""

    def __init__(self, missing: tuple[Point, ...]) -> None:
        self.missing = missing
        names = ", ".join(p.value for p in missing)
        super().__init__(f"falta la pareja de escala: {names}")


def scale_pair_for(view: View) -> tuple[Point, Point]:
    """Qué dos puntos normalizan las distancias en esta vista."""
    if is_profile(view):
        return SCALE_PAIR["profile"]
    if view is View.BASAL:
        return SCALE_PAIR["basal"]
    return SCALE_PAIR["frontal"]


def reference_scale(view: View, points: dict[Point, MarkedPoint]) -> float:
    """La distancia de referencia de una vista, en píxeles.

    Intercantal en frontal; longitud del plano de Frankfort en perfil,
    que es el otro par estable disponible cuando no se ven los dos ojos.

    Se calcula sobre el CONSENSO de cada punto, no sobre su primera
    marca: si la pareja de escala llevara doble marcado, usar una sola
    pasada metería el error de esa marca en el denominador de todas las
    demás discrepancias.
    """
    a, b = scale_pair_for(view)
    missing = tuple(p for p in (a, b) if p not in points)
    if missing:
        raise MissingScalePoints(missing)
    d = distance(points[a].consensus, points[b].consensus)
    if d <= 0:
        raise ValueError("la distancia de referencia debe ser positiva")
    return float(d)


@dataclass(frozen=True, slots=True)
class MarkedPoint:
    """Un punto con una o dos pasadas de marcado."""

    point: Point
    passes: tuple[Vec, ...]

    def __post_init__(self) -> None:
        if not self.passes:
            raise ValueError(f"{self.point.value}: sin ninguna marca")
        if len(self.passes) > 2:
            raise ValueError(f"{self.point.value}: se esperaban 1 o 2 pasadas")

    @property
    def consensus(self) -> Vec:
        """El punto que se usa para medir: la media de las pasadas."""
        return np.mean([as_point(p) for p in self.passes], axis=0)

    @property
    def discrepancy(self) -> float:
        """Distancia entre las dos marcas. 0 si solo hay una."""
        if len(self.passes) < 2:
            return 0.0
        return distance(self.passes[0], self.passes[1])

    @property
    def double_marked(self) -> bool:
        return len(self.passes) == 2

    def sigma(self, scale: float) -> float:
        """Desviación estándar por eje, normalizada por `scale`.

        Derivación, porque el factor no es obvio: si las dos marcas A y B
        son observaciones independientes del punto verdadero, cada una
        con error gaussiano N(0, σ²) en cada eje, entonces la diferencia
        D = A − B tiene varianza 2σ² por eje, y el módulo |D| en 2D sigue
        una Rayleigh con E[|D|] = σ·√π.

        Así que σ ≈ |D| / √π. No es un factor elegido a ojo.
        """
        if not self.double_marked:
            return SINGLE_MARK_SIGMA
        return (self.discrepancy / scale) / math.sqrt(math.pi)


@dataclass(frozen=True, slots=True)
class MarkingSet:
    """El marcado completo de una vista, con su escala de referencia."""

    points: dict[Point, MarkedPoint]
    #: Distancia estable intra-imagen que normaliza todo lo demás. En
    #: frontal, la distancia intercantal. En perfil no hay intercantal,
    #: así que se usa la longitud del plano de Frankfort (porion a
    #: orbitale), que es el otro par estable disponible.
    scale: float
    capture_grade: CaptureGrade = "A"
    tolerance: float = DEFAULT_TOLERANCE

    def __post_init__(self) -> None:
        if self.scale <= 0:
            raise ValueError("la distancia de referencia debe ser positiva")

    def consensus_map(self) -> PointMap:
        return {p: mp.consensus for p, mp in self.points.items()}

    def normalized_discrepancy(self, point: Point) -> float:
        mp = self.points.get(point)
        return 0.0 if mp is None else mp.discrepancy / self.scale

    def unreliable_points(self) -> tuple[Point, ...]:
        """Puntos frágiles cuyas dos marcas no se pusieron de acuerdo.

        Solo se evalúan los frágiles con doble marcado: un punto marcado
        una vez no tiene con qué contradecirse, y eso NO lo vuelve
        fiable — lo que hace es que su incertidumbre sea la del suelo
        (`SINGLE_MARK_SIGMA`), que igualmente ensancha la banda.
        """
        out = []
        for p, mp in self.points.items():
            if p in FRAGILE_POINTS and mp.double_marked:
                if mp.discrepancy / self.scale > self.tolerance:
                    out.append(p)
        return tuple(sorted(out, key=lambda x: x.value))

    def missing_double_marks(self) -> tuple[Point, ...]:
        """Frágiles que se marcaron una sola vez. Es un fallo de flujo."""
        return tuple(
            sorted(
                (p for p, mp in self.points.items() if p in FRAGILE_POINTS and not mp.double_marked),
                key=lambda x: x.value,
            )
        )


def propagate_error(
    spec: MetricSpec,
    marking: MarkingSet,
    *,
    samples: int = 512,
    seed: int = 0,
) -> float:
    """Banda de error de la métrica, por muestreo Monte Carlo.

    Perturba cada punto según su dispersión observada, recalcula la
    métrica, y devuelve la desviación estándar del resultado. Se hace
    numéricamente en vez de con derivadas analíticas porque las métricas
    son heterogéneas (ángulos, ratios, porcentajes) y una fórmula por
    métrica sería otra cosa más que mantener y que se puede desincronizar
    del cálculo.

    Determinista: la semilla es explícita y por defecto fija.
    """
    rng = np.random.default_rng(seed)
    grade = GRADE_FACTOR[marking.capture_grade]

    # Se perturban TODOS los puntos presentes, no solo los que la métrica
    # declara: si necesita alineación a Frankfort, porion y orbitale
    # también mueven el resultado aunque no estén en `depends_on`.
    sigmas = {
        p: mp.sigma(marking.scale) * grade * marking.scale
        for p, mp in marking.points.items()
    }
    base = marking.consensus_map()

    values: list[float] = []
    for _ in range(samples):
        perturbed = {
            p: v + rng.normal(0.0, sigmas[p], size=2) for p, v in base.items()
        }
        try:
            values.append(spec.evaluate(perturbed))
        except (ValueError, ZeroDivisionError):
            # Una muestra degenerada (dos puntos que caen encima) no
            # invalida la estimación; se descarta.
            continue

    if len(values) < 2:
        raise ValueError(f"{spec.name}: no se pudo estimar la banda de error")
    return float(np.std(values, ddof=1))

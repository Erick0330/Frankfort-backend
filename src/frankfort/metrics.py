"""Catálogo de métricas. Cada una declara de qué puntos depende.

Esa declaración no es documentación: es el grafo que usa el auditor para
invalidar en cascada. Si un punto sale poco fiable, todas las métricas
que lo listan se suprimen, sin que nadie tenga que acordarse.

DOS RESTRICCIONES DURAS, ambas del §0 de la arquitectura:

1. **Prohibido el milímetro.** `Unit` no incluye longitudes absolutas.
   La fotogrametría 2D no da escala fiable, así que solo ángulos y
   ratios adimensionales. Está en el tipo para que no se pueda colar.

2. **El rango de referencia no es un objetivo.** Es el intervalo donde
   cae la mayoría de la población medida en la literatura. Sirve para
   una sola cosa: decidir si la banda de error de una medición es tan
   ancha que la métrica no puede distinguir señal de ruido.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from .geometry import (
    Vec,
    align_to_frankfort,
    angle_at,
    angle_to_horizontal,
    distance,
    horizontal_extent,
    vertical_extent,
)
from .landmarks import Point, View

#: Sin "mm" ni "cm" a propósito. Ver la restricción 1 del docstring.
Unit = Literal["deg", "ratio", "percent"]

PointMap = Mapping[Point, Vec]


class MissingPoints(Exception):
    """Faltan puntos para calcular la métrica."""

    def __init__(self, metric: str, missing: tuple[Point, ...]) -> None:
        self.metric = metric
        self.missing = missing
        super().__init__(f"{metric}: faltan {[p.value for p in missing]}")


@dataclass(frozen=True, slots=True)
class MetricSpec:
    name: str
    unit: Unit
    #: El grafo de dependencias. Orden irrelevante, contenido crítico.
    depends_on: tuple[Point, ...]
    #: Rango poblacional de referencia. NO un objetivo estético.
    reference: tuple[float, float]
    compute: Callable[[PointMap], float]
    #: Si es True, hay que alinear a Frankfort antes de medir. Los
    #: ángulos entre tres puntos faciales son invariantes a rotación y
    #: no lo necesitan; los referidos a horizontal o vertical sí.
    needs_frankfort: bool
    views: tuple[View, ...]
    description: str

    def evaluate(self, points: PointMap) -> float:
        missing = tuple(p for p in self.depends_on if p not in points)
        if missing:
            raise MissingPoints(self.name, missing)
        pts = points
        if self.needs_frankfort:
            for ref in (Point.PORION, Point.ORBITALE):
                if ref not in points:
                    raise MissingPoints(self.name, (ref,))
            aligned = align_to_frankfort(
                {p.value: v for p, v in points.items()},
                points[Point.PORION],
                points[Point.ORBITALE],
            )
            pts = {Point(k): v for k, v in aligned.items()}
        return float(self.compute(pts))


# ─────────────────────────── perfil nasal ───────────────────────────


def _goode_ratio(p: PointMap) -> float:
    """Proyección de la punta / longitud del dorso.

    La proyección se mide PERPENDICULAR a la vertical verdadera, de ahí
    `horizontal_extent` y de ahí que necesite alineación a Frankfort.
    Medirla como distancia en línea recta es el error clásico y da
    valores infladas.
    """
    projection = horizontal_extent(p[Point.ALAR_CREASE], p[Point.PRONASALE])
    dorsum = distance(p[Point.NASION], p[Point.PRONASALE])
    if dorsum == 0:
        raise ValueError("goode_ratio: dorso de longitud cero")
    return projection / dorsum


def _nasolabial_angle(p: PointMap) -> float:
    return angle_at(
        p[Point.SUBNASALE], p[Point.COLUMELLA_APEX], p[Point.LABRALE_SUPERIUS]
    )


def _nasofrontal_angle(p: PointMap) -> float:
    return angle_at(p[Point.NASION], p[Point.GLABELLA], p[Point.PRONASALE])


def _facial_convexity(p: PointMap) -> float:
    return angle_at(p[Point.SUBNASALE], p[Point.GLABELLA], p[Point.POGONION])


# ─────────────────────── tercios verticales ─────────────────────────
#
# El reparto de dependencias de aquí es el corazón del caso que cuenta
# la landing. Fíjate en cuál NO depende de Subnasale:
#
#   superior : trichion → glabella      (sin Subnasale)
#   medio    : glabella → subnasale     (con Subnasale)
#   inferior : subnasale → menton       (con Subnasale)
#
# Todas dividen por la altura total (trichion → menton). Así que si
# Subnasale sale poco fiable, el auditor suprime el medio y el inferior
# y conserva el superior — sin ninguna regla especial, solo siguiendo el
# grafo. Uno de tres se salva.


def _total_face_height(p: PointMap) -> float:
    h = vertical_extent(p[Point.TRICHION], p[Point.MENTON])
    if h == 0:
        raise ValueError("tercios: altura facial de cero")
    return h


def _upper_third(p: PointMap) -> float:
    return 100.0 * vertical_extent(p[Point.TRICHION], p[Point.GLABELLA]) / _total_face_height(p)


def _middle_third(p: PointMap) -> float:
    return 100.0 * vertical_extent(p[Point.GLABELLA], p[Point.SUBNASALE]) / _total_face_height(p)


def _lower_third(p: PointMap) -> float:
    return 100.0 * vertical_extent(p[Point.SUBNASALE], p[Point.MENTON]) / _total_face_height(p)


# ──────────────────────────── mandíbula ─────────────────────────────


def _mandibular_plane_angle(p: PointMap) -> float:
    """Ángulo del plano mandibular (gonion→menton) contra la horizontal.

    Presupone alineación a Frankfort, así que "horizontal" ES el plano
    de Frankfort. Con la cara alineada, `menton` queda por debajo de
    `gonion` y la inclinación sale negativa; se devuelve el valor
    absoluto, que es como se reporta en la literatura.

    OJO — el rango es ~22-28°, no ~120°. Ver la nota de discrepancia en
    docs/05-discrepancias.md: la landing publicada dice "122°", que es
    el ángulo gonial (entre rama y cuerpo mandibular) y necesita un
    punto de la rama que no está en el set. Con Gonion, Menton, Porion y
    Orbitale —los cuatro que la propia landing declara— lo que sale es
    esto.
    """
    return abs(angle_to_horizontal(p[Point.GONION_R], p[Point.MENTON]))



# ───────────────────────────── frontal ──────────────────────────────
#
# En frontal no hay plano de Frankfort —porion y orbitale no se ven—, así
# que la referencia es la LÍNEA INTERCANTAL: la que une las dos esquinas
# internas de los ojos. Es la pareja de escala de la vista, tiene bordes
# nítidos, y la mitad entre las dos marca la línea media.
#
# Todas las frontales se miden en ese marco: `u` en horizontal sobre la
# línea intercantal (positivo hacia el lado izquierdo del sujeto) y `v`
# en vertical, perpendicular a ella (positivo hacia abajo). Así una
# cabeza un poco ladeada en la foto no contamina ni la inclinación de los
# ojos ni la desviación de la línea media: se mide contra la cara, no
# contra el borde de la imagen.


def _canthal_frame(p: PointMap) -> tuple[Vec, Vec, Vec, float]:
    """Origen, eje u, eje v y anchura intercantal."""
    import numpy as np

    en_r = np.asarray(p[Point.ENDOCANTHION_R], dtype=np.float64)
    en_l = np.asarray(p[Point.ENDOCANTHION_L], dtype=np.float64)
    width = float(np.linalg.norm(en_l - en_r))
    if width == 0:
        raise ValueError("frontal: anchura intercantal de cero")
    ex = (en_l - en_r) / width
    ey = np.array([-ex[1], ex[0]])  # perpendicular, hacia abajo
    return (en_r + en_l) / 2, ex, ey, width


def _uv(q: Vec, frame: tuple[Vec, Vec, Vec, float]) -> tuple[float, float]:
    import numpy as np

    o, ex, ey, _ = frame
    d = np.asarray(q, dtype=np.float64) - o
    return float(d @ ex), float(d @ ey)


def _horizontal_fifths(p: PointMap) -> float:
    """Hueco entre los ojos / ancho medio de un ojo.

    El canon de los quintos dice que la cara mide cinco ojos de ancho, y
    que el hueco entre los ojos es uno de esos quintos. Esto mide la parte
    del canon que se puede medir con nitidez: si el quinto central es del
    mismo tamaño que los de los ojos. 1,0 es el canon; la población real,
    según Farkas, cae algo por encima.
    """
    eye_r = distance(p[Point.ENDOCANTHION_R], p[Point.EXOCANTHION_R])
    eye_l = distance(p[Point.ENDOCANTHION_L], p[Point.EXOCANTHION_L])
    mean_eye = (eye_r + eye_l) / 2
    if mean_eye == 0:
        raise ValueError("quintos: ancho de ojo de cero")
    return distance(p[Point.ENDOCANTHION_R], p[Point.ENDOCANTHION_L]) / mean_eye


def _facial_index(p: PointMap) -> float:
    """Altura de la cara (nasion→gnathion) / anchura (cigomática) × 100.

    Es el índice facial morfológico de la antropometría clásica. Las dos
    distancias se miden en el marco intercantal: la altura sobre la
    vertical de la cara y la anchura sobre su horizontal, no en diagonal.
    """
    f = _canthal_frame(p)
    _, v_n = _uv(p[Point.NASION], f)
    _, v_gn = _uv(p[Point.GNATHION], f)
    u_zr, _ = _uv(p[Point.ZYGION_R], f)
    u_zl, _ = _uv(p[Point.ZYGION_L], f)
    width = abs(u_zl - u_zr)
    if width == 0:
        raise ValueError("índice facial: anchura cigomática de cero")
    return 100.0 * abs(v_gn - v_n) / width


def _midline_deviation(p: PointMap) -> float:
    """Cuánto se aparta de la línea media la base de la nariz o el mentón.

    La línea media es la perpendicular a la intercantal por su punto
    medio. Se toma el MAYOR de los dos desvíos, en porcentaje de la
    anchura intercantal — así el número no depende de lo cerca que se
    hiciera la foto.
    """
    f = _canthal_frame(p)
    u_sn, _ = _uv(p[Point.SUBNASALE], f)
    u_me, _ = _uv(p[Point.MENTON], f)
    return 100.0 * max(abs(u_sn), abs(u_me)) / f[3]


def _canthal_tilt(p: PointMap) -> float:
    """Inclinación de los ojos: media de los dos lados, en grados.

    Positivo = la esquina EXTERNA queda más alta que la interna. Se mide
    contra la línea intercantal, no contra la horizontal de la foto, así
    que una cabeza ladeada no cambia el resultado.
    """
    import numpy as np

    f = _canthal_frame(p)
    tilts = []
    for en, ex in (
        (Point.ENDOCANTHION_R, Point.EXOCANTHION_R),
        (Point.ENDOCANTHION_L, Point.EXOCANTHION_L),
    ):
        u_en, v_en = _uv(p[en], f)
        u_ex, v_ex = _uv(p[ex], f)
        dx = abs(u_ex - u_en)
        if dx == 0:
            raise ValueError("inclinación de ojos: ojo de ancho cero")
        tilts.append(float(np.degrees(np.arctan2(v_en - v_ex, dx))))
    return sum(tilts) / 2

# ────────────────────────────── basal ───────────────────────────────
#
# La cara vista desde abajo: se ven las dos aletas de la nariz, la
# columela y la punta. Es la única vista donde una desviación leve de la
# nariz es inequívoca — de frente se confunde con la pose y de perfil no
# se ve. La referencia es la línea que une las dos aletas (alare–alare);
# el eje de la nariz debería caer perpendicular a ella.


def _alar_frame(p: PointMap) -> tuple[Vec, Vec, Vec, float]:
    """Origen en el punto medio de las aletas, eje u sobre la línea de
    aletas (hacia la izquierda del sujeto), eje v perpendicular."""
    import numpy as np

    al_r = np.asarray(p[Point.ALARE_R], dtype=np.float64)
    al_l = np.asarray(p[Point.ALARE_L], dtype=np.float64)
    width = float(np.linalg.norm(al_l - al_r))
    if width == 0:
        raise ValueError("basal: anchura alar de cero")
    ex = (al_l - al_r) / width
    ey = np.array([-ex[1], ex[0]])
    return (al_r + al_l) / 2, ex, ey, width


def _nasal_axis_deviation(p: PointMap) -> float:
    """Ángulo entre el eje de la nariz y la perpendicular a las aletas.

    El eje es la columela: de subnasale (la base) a pronasale (la punta).
    En una nariz centrada es perpendicular a la línea de las aletas; el
    ángulo que se aparta es la desviación. Sin signo: el informe dice
    cuánto, y hacia qué lado no cambia ninguna recomendación.
    """
    import numpy as np

    _, ex, ey, _ = _alar_frame(p)
    axis = np.asarray(p[Point.PRONASALE], dtype=np.float64) - np.asarray(
        p[Point.SUBNASALE], dtype=np.float64
    )
    n = float(np.linalg.norm(axis))
    if n == 0:
        raise ValueError("eje nasal: columela de longitud cero")
    along = abs(float(axis @ ey))
    across = abs(float(axis @ ex))
    return float(np.degrees(np.arctan2(across, along)))


def _alar_base_symmetry(p: PointMap) -> float:
    """Diferencia entre las dos mitades de la base nasal, en %.

    Se mide la distancia de cada aleta al eje de la columela; con una
    base simétrica son iguales. Se devuelve |d_der − d_izq| sobre la
    suma, por cien: 0 es simetría perfecta, y el número no depende de lo
    cerca que se hiciera la foto.
    """
    from .geometry import perpendicular_distance

    d_r = perpendicular_distance(p[Point.ALARE_R], p[Point.SUBNASALE], p[Point.PRONASALE])
    d_l = perpendicular_distance(p[Point.ALARE_L], p[Point.SUBNASALE], p[Point.PRONASALE])
    total = d_r + d_l
    if total == 0:
        raise ValueError("simetría alar: aletas sobre el eje")
    return 100.0 * abs(d_r - d_l) / total


# ──────────────────────────── el registro ───────────────────────────

PROFILE_VIEWS = (View.PROFILE_RIGHT, View.PROFILE_LEFT)

REGISTRY: tuple[MetricSpec, ...] = (
    MetricSpec(
        name="goode_ratio",
        unit="ratio",
        depends_on=(Point.ALAR_CREASE, Point.PRONASALE, Point.NASION),
        reference=(0.55, 0.60),
        compute=_goode_ratio,
        needs_frankfort=True,
        views=PROFILE_VIEWS,
        description="Proyección de la punta nasal relativa a la longitud del dorso.",
    ),
    MetricSpec(
        name="nasolabial_angle",
        unit="deg",
        depends_on=(Point.SUBNASALE, Point.COLUMELLA_APEX, Point.LABRALE_SUPERIUS),
        reference=(90.0, 110.0),
        compute=_nasolabial_angle,
        needs_frankfort=False,
        views=PROFILE_VIEWS,
        description="Ángulo entre columela y labio superior en subnasale.",
    ),
    MetricSpec(
        name="nasofrontal_angle",
        unit="deg",
        depends_on=(Point.NASION, Point.GLABELLA, Point.PRONASALE),
        reference=(115.0, 130.0),
        compute=_nasofrontal_angle,
        needs_frankfort=False,
        views=PROFILE_VIEWS,
        description="Ángulo de la raíz nasal entre glabela y punta.",
    ),
    MetricSpec(
        name="facial_convexity_angle",
        unit="deg",
        depends_on=(Point.GLABELLA, Point.SUBNASALE, Point.POGONION),
        reference=(165.0, 175.0),
        compute=_facial_convexity,
        needs_frankfort=False,
        views=PROFILE_VIEWS,
        description="Convexidad del perfil entre glabela, subnasale y pogonion.",
    ),
    MetricSpec(
        name="upper_third_pct",
        unit="percent",
        depends_on=(Point.TRICHION, Point.GLABELLA, Point.MENTON),
        reference=(30.0, 36.0),
        compute=_upper_third,
        needs_frankfort=True,
        views=(View.FRONTAL_REST,) + PROFILE_VIEWS,
        description="Tercio superior como porcentaje de la altura facial.",
    ),
    MetricSpec(
        name="middle_third_pct",
        unit="percent",
        depends_on=(Point.TRICHION, Point.GLABELLA, Point.SUBNASALE, Point.MENTON),
        reference=(30.0, 36.0),
        compute=_middle_third,
        needs_frankfort=True,
        views=(View.FRONTAL_REST,) + PROFILE_VIEWS,
        description="Tercio medio como porcentaje de la altura facial.",
    ),
    MetricSpec(
        name="lower_third_pct",
        unit="percent",
        depends_on=(Point.TRICHION, Point.SUBNASALE, Point.MENTON),
        reference=(30.0, 36.0),
        compute=_lower_third,
        needs_frankfort=True,
        views=(View.FRONTAL_REST,) + PROFILE_VIEWS,
        description="Tercio inferior como porcentaje de la altura facial.",
    ),
    MetricSpec(
        name="mandibular_plane_angle",
        unit="deg",
        depends_on=(Point.GONION_R, Point.MENTON),
        reference=(22.0, 28.0),
        compute=_mandibular_plane_angle,
        needs_frankfort=True,
        views=PROFILE_VIEWS,
        description="Inclinación del plano mandibular respecto al plano de Frankfort.",
    ),
)


#: Las de la vista frontal. Van aparte porque se miden contra la línea
#: intercantal, no contra Frankfort: `needs_frankfort=False` en todas.
#:
#: Los rangos son de la antropometría de Farkas (Anthropometry of the
#: Head and Face, 1994), redondeados a la banda donde cae la mayoría de
#: los adultos. Como el resto del registro: no son un objetivo.
FRONTAL_VIEWS = (View.FRONTAL_REST,)

REGISTRY = REGISTRY + (
    MetricSpec(
        name="horizontal_fifths",
        unit="ratio",
        depends_on=(
            Point.ENDOCANTHION_R,
            Point.ENDOCANTHION_L,
            Point.EXOCANTHION_R,
            Point.EXOCANTHION_L,
        ),
        reference=(0.9, 1.25),
        compute=_horizontal_fifths,
        needs_frankfort=False,
        views=FRONTAL_VIEWS,
        description="Hueco entre los ojos respecto al ancho medio de un ojo.",
    ),
    MetricSpec(
        name="facial_index",
        unit="percent",
        depends_on=(
            Point.ENDOCANTHION_R,
            Point.ENDOCANTHION_L,
            Point.NASION,
            Point.GNATHION,
            Point.ZYGION_R,
            Point.ZYGION_L,
        ),
        reference=(83.0, 93.0),
        compute=_facial_index,
        needs_frankfort=False,
        views=FRONTAL_VIEWS,
        description="Altura facial (nasion–gnathion) sobre anchura cigomática.",
    ),
    MetricSpec(
        name="midline_deviation",
        unit="percent",
        depends_on=(
            Point.ENDOCANTHION_R,
            Point.ENDOCANTHION_L,
            Point.SUBNASALE,
            Point.MENTON,
        ),
        reference=(0.0, 8.0),
        compute=_midline_deviation,
        needs_frankfort=False,
        views=FRONTAL_VIEWS,
        description="Mayor desvío de la base nasal o del mentón respecto a la línea media.",
    ),
    MetricSpec(
        name="canthal_tilt",
        unit="deg",
        depends_on=(
            Point.ENDOCANTHION_R,
            Point.ENDOCANTHION_L,
            Point.EXOCANTHION_R,
            Point.EXOCANTHION_L,
        ),
        reference=(0.0, 8.0),
        compute=_canthal_tilt,
        needs_frankfort=False,
        views=FRONTAL_VIEWS,
        description="Inclinación media de la línea entre las esquinas de cada ojo.",
    ),
)

#: Las de la basal. Mismo criterio que las frontales: se miden contra
#: una referencia de la propia cara (la línea de las aletas), no contra
#: Frankfort, que desde abajo no se ve.
BASAL_VIEWS = (View.BASAL,)

REGISTRY = REGISTRY + (
    MetricSpec(
        name="nasal_axis_deviation",
        unit="deg",
        depends_on=(Point.ALARE_R, Point.ALARE_L, Point.SUBNASALE, Point.PRONASALE),
        reference=(0.0, 4.0),
        compute=_nasal_axis_deviation,
        needs_frankfort=False,
        views=BASAL_VIEWS,
        description="Desvío del eje de la columela respecto a la perpendicular a las aletas.",
    ),
    MetricSpec(
        name="alar_base_symmetry",
        unit="percent",
        depends_on=(Point.ALARE_R, Point.ALARE_L, Point.SUBNASALE, Point.PRONASALE),
        reference=(0.0, 10.0),
        compute=_alar_base_symmetry,
        needs_frankfort=False,
        views=BASAL_VIEWS,
        description="Diferencia entre las dos mitades de la base nasal.",
    ),
)

BY_NAME: dict[str, MetricSpec] = {m.name: m for m in REGISTRY}


def metrics_depending_on(point: Point) -> tuple[MetricSpec, ...]:
    """Todas las métricas que se caen si `point` no es fiable."""
    return tuple(m for m in REGISTRY if point in m.depends_on)

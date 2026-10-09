"""Primitivas geométricas. numpy puro, cero ML, cero LLM.

Todo lo que mide el sistema pasa por aquí. Es la capa donde un error se
propaga a todo el informe, así que va con tests de respuesta exacta.

Convenio de coordenadas: origen arriba-izquierda, `y` crece hacia abajo
(el convenio de una imagen). Importa para el signo de los ángulos.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

Vec = NDArray[np.float64]


def as_point(xy: tuple[float, float] | Vec) -> Vec:
    """Normaliza cualquier par a un array de float64 de forma (2,)."""
    p = np.asarray(xy, dtype=np.float64)
    if p.shape != (2,):
        raise ValueError(f"se esperaba un punto 2D, llegó forma {p.shape}")
    return p


def distance(a: Vec, b: Vec) -> float:
    """Distancia euclídea. En unidades de la imagen, nunca en mm."""
    return float(np.linalg.norm(as_point(b) - as_point(a)))


def angle_at(vertex: Vec, a: Vec, b: Vec) -> float:
    """Ángulo interior en `vertex` entre los rayos a `a` y a `b`, en grados.

    Siempre en [0, 180]. Es el ángulo sin signo — el que se usa para
    nasolabial, nasofrontal y convexidad facial.
    """
    v = as_point(vertex)
    u1 = as_point(a) - v
    u2 = as_point(b) - v
    n1 = np.linalg.norm(u1)
    n2 = np.linalg.norm(u2)
    if n1 == 0 or n2 == 0:
        raise ValueError("ángulo indefinido: el vértice coincide con un extremo")
    # clip porque el redondeo de float puede dar |cos| = 1 + 1e-16
    cos = float(np.clip(np.dot(u1, u2) / (n1 * n2), -1.0, 1.0))
    return float(np.degrees(np.arccos(cos)))


def angle_to_horizontal(a: Vec, b: Vec) -> float:
    """Inclinación del segmento a→b respecto a la horizontal, en grados.

    Positivo = el extremo `b` queda MÁS ALTO que `a` en pantalla. Se
    corrige el signo de `y` para que "más alto" sea positivo, porque en
    coordenadas de imagen `y` crece hacia abajo y lo contrario sería una
    fuente constante de errores de signo.
    """
    p, q = as_point(a), as_point(b)
    dx = q[0] - p[0]
    dy = -(q[1] - p[1])
    if dx == 0 and dy == 0:
        raise ValueError("inclinación indefinida: los dos puntos coinciden")
    return float(np.degrees(np.arctan2(dy, dx)))


def rotate(points: dict[str, Vec], degrees: float, about: Vec) -> dict[str, Vec]:
    """Rota un conjunto de puntos alrededor de `about`."""
    t = np.radians(degrees)
    # `y` invertida: rotación antihoraria en pantalla
    c, s = np.cos(t), np.sin(t)
    m = np.array([[c, s], [-s, c]], dtype=np.float64)
    o = as_point(about)
    return {k: o + m @ (as_point(v) - o) for k, v in points.items()}


def align_to_frankfort(
    points: dict[str, Vec], porion: Vec, orbitale: Vec
) -> dict[str, Vec]:
    """Rota la cara para que el plano de Frankfort quede horizontal.

    Es un paso obligatorio antes de medir cualquier ángulo referido a la
    horizontal o a la vertical verdadera. Sin esto, una cabeza inclinada
    2° contamina todos esos ángulos por igual — y es el error de pose más
    común en fotos de perfil.

    Los ángulos entre tres puntos faciales (nasolabial, nasofrontal) son
    invariantes a rotación y no lo necesitan; los referidos a la
    horizontal (ángulo mandibular, canthal tilt) sí.
    """
    tilt = angle_to_horizontal(porion, orbitale)
    return rotate(points, -tilt, about=porion)


def project_onto_line(p: Vec, a: Vec, b: Vec) -> Vec:
    """Proyección ortogonal de `p` sobre la recta que pasa por `a` y `b`."""
    pa, pb, pp = as_point(a), as_point(b), as_point(p)
    d = pb - pa
    n2 = float(np.dot(d, d))
    if n2 == 0:
        raise ValueError("recta indefinida: `a` y `b` coinciden")
    t = float(np.dot(pp - pa, d)) / n2
    return pa + t * d


def perpendicular_distance(p: Vec, a: Vec, b: Vec) -> float:
    """Distancia de `p` a la recta a–b. Sin signo."""
    return distance(as_point(p), project_onto_line(p, a, b))


def horizontal_extent(a: Vec, b: Vec) -> float:
    """Distancia horizontal absoluta. Presupone alineación a Frankfort.

    Es el numerador del ratio de Goode: la proyección de la punta nasal
    se mide perpendicular a la vertical verdadera, no en línea recta.
    """
    return float(abs(as_point(b)[0] - as_point(a)[0]))


def vertical_extent(a: Vec, b: Vec) -> float:
    """Distancia vertical absoluta. Presupone alineación a Frankfort."""
    return float(abs(as_point(b)[1] - as_point(a)[1]))

"""Primitivas geométricas, con respuestas exactas verificables a mano."""

from __future__ import annotations

import math

import numpy as np
import pytest

from frankfort.geometry import (
    align_to_frankfort,
    angle_at,
    angle_to_horizontal,
    distance,
    horizontal_extent,
    perpendicular_distance,
    project_onto_line,
    rotate,
    vertical_extent,
)


def p(x: float, y: float) -> np.ndarray:
    return np.array([x, y], dtype=np.float64)


class TestAngleAt:
    def test_right_angle_is_exactly_90(self):
        assert angle_at(p(0, 0), p(1, 0), p(0, 1)) == pytest.approx(90.0)

    def test_straight_line_is_180(self):
        assert angle_at(p(0, 0), p(1, 0), p(-1, 0)) == pytest.approx(180.0)

    def test_equilateral_is_60(self):
        assert angle_at(p(0, 0), p(1, 0), p(0.5, math.sqrt(3) / 2)) == pytest.approx(60.0)

    def test_invariant_to_rotation(self):
        """Los ángulos entre tres puntos no cambian al rotar la cara.

        Es la razón de que nasolabial y nasofrontal no necesiten
        alineación a Frankfort. Si esto se rompiera, media docena de
        métricas empezarían a depender de la pose.
        """
        pts = {"v": p(0, 0), "a": p(3, 1), "b": p(-2, 4)}
        before = angle_at(pts["v"], pts["a"], pts["b"])
        rot = rotate(pts, 37.0, about=p(10, 10))
        after = angle_at(rot["v"], rot["a"], rot["b"])
        assert after == pytest.approx(before)

    def test_degenerate_vertex_raises(self):
        with pytest.raises(ValueError, match="indefinido"):
            angle_at(p(0, 0), p(0, 0), p(1, 1))


class TestAngleToHorizontal:
    def test_flat_is_zero(self):
        assert angle_to_horizontal(p(0, 5), p(10, 5)) == pytest.approx(0.0)

    def test_upward_is_positive_on_screen(self):
        """`y` crece hacia abajo, así que subir en pantalla es y menor.

        Se comprueba explícitamente porque el signo aquí es la fuente de
        error más probable de todo el módulo.
        """
        assert angle_to_horizontal(p(0, 10), p(10, 0)) == pytest.approx(45.0)

    def test_downward_is_negative(self):
        assert angle_to_horizontal(p(0, 0), p(10, 10)) == pytest.approx(-45.0)

    def test_known_3_4_5(self):
        assert angle_to_horizontal(p(0, 0), p(40, -30)) == pytest.approx(
            math.degrees(math.atan2(30, 40))
        )


class TestFrankfortAlignment:
    def test_already_level_is_unchanged(self):
        pts = {"a": p(20, 20), "b": p(80, 60)}
        out = align_to_frankfort({**pts}, porion=p(10, 45), orbitale=p(70, 45))
        assert out["a"] == pytest.approx(pts["a"])
        assert out["b"] == pytest.approx(pts["b"])

    def test_tilted_plane_becomes_horizontal(self):
        porion = p(10, 45)
        orbitale = p(10 + 60 * math.cos(math.radians(-12)), 45 + 60 * math.sin(math.radians(12)))
        pts = {"po": porion, "or": orbitale}
        out = align_to_frankfort(pts, porion, orbitale)
        assert angle_to_horizontal(out["po"], out["or"]) == pytest.approx(0.0, abs=1e-9)

    def test_alignment_preserves_distances(self):
        """Rotar no puede cambiar longitudes. Si las cambiara, todos los
        ratios se contaminarían con la pose."""
        pts = {"a": p(0, 0), "b": p(30, 40)}
        d_before = distance(pts["a"], pts["b"])
        out = align_to_frankfort(pts, porion=p(5, 5), orbitale=p(65, 20))
        assert distance(out["a"], out["b"]) == pytest.approx(d_before)


class TestProjection:
    def test_projection_onto_horizontal_line(self):
        got = project_onto_line(p(5, 20), p(0, 0), p(10, 0))
        assert got == pytest.approx(p(5, 0))

    def test_perpendicular_distance_is_exact(self):
        assert perpendicular_distance(p(0, 7), p(0, 0), p(10, 0)) == pytest.approx(7.0)

    def test_degenerate_line_raises(self):
        with pytest.raises(ValueError, match="indefinida"):
            project_onto_line(p(1, 1), p(2, 2), p(2, 2))


class TestExtents:
    def test_horizontal_extent_ignores_vertical(self):
        assert horizontal_extent(p(10, 0), p(35, 100)) == pytest.approx(25.0)

    def test_vertical_extent_ignores_horizontal(self):
        assert vertical_extent(p(0, 10), p(100, 35)) == pytest.approx(25.0)

    def test_extents_are_unsigned(self):
        assert horizontal_extent(p(35, 0), p(10, 0)) == pytest.approx(25.0)
        assert vertical_extent(p(0, 35), p(0, 10)) == pytest.approx(25.0)

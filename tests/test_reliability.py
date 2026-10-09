"""Doble marcado, dispersión y propagación de error."""

from __future__ import annotations

import math

import pytest

from frankfort.landmarks import Point
from frankfort.metrics import BY_NAME
from frankfort.reliability import (
    GRADE_FACTOR,
    SINGLE_MARK_SIGMA,
    MarkedPoint,
    MarkingSet,
    propagate_error,
)

from .conftest import FRANKFORT_SCALE, double, frankfort_points, p, single


class TestMarkedPoint:
    def test_consensus_is_the_midpoint(self):
        mp = double(Point.SUBNASALE, (10.0, 20.0), (14.0, 24.0))
        assert mp.consensus == pytest.approx(p(12.0, 22.0))

    def test_discrepancy_is_the_distance_between_passes(self):
        mp = double(Point.SUBNASALE, (0.0, 0.0), (3.0, 4.0))
        assert mp.discrepancy == pytest.approx(5.0)

    def test_single_mark_has_no_discrepancy_but_still_has_uncertainty(self):
        """Un punto marcado una vez no puede contradecirse — y eso NO lo
        vuelve exacto. Sigue arrastrando la incertidumbre del suelo."""
        mp = single(Point.COLUMELLA_APEX, 5.0, 5.0)
        assert mp.discrepancy == 0.0
        assert mp.sigma(FRANKFORT_SCALE) == SINGLE_MARK_SIGMA

    def test_sigma_uses_the_rayleigh_factor(self):
        """σ ≈ |D| / √π, derivado en el docstring de `sigma`.

        Se comprueba el factor porque es justo el tipo de constante que
        alguien "simplifica" a /2 sin darse cuenta de que cambia todas
        las bandas de error del informe.
        """
        mp = double(Point.SUBNASALE, (0.0, 0.0), (6.0, 0.0))
        expected = (6.0 / FRANKFORT_SCALE) / math.sqrt(math.pi)
        assert mp.sigma(FRANKFORT_SCALE) == pytest.approx(expected)

    def test_rejects_empty_and_triple(self):
        with pytest.raises(ValueError, match="sin ninguna marca"):
            MarkedPoint(Point.SUBNASALE, ())
        with pytest.raises(ValueError, match="1 o 2 pasadas"):
            MarkedPoint(Point.SUBNASALE, (p(0, 0), p(1, 1), p(2, 2)))


class TestUnreliableDetection:
    def test_tight_double_marks_are_reliable(self, thirds_marking: MarkingSet):
        assert thirds_marking.unreliable_points() == ()

    def test_wide_double_marks_flag_the_point(
        self, thirds_marking_bad_subnasale: MarkingSet
    ):
        assert thirds_marking_bad_subnasale.unreliable_points() == (Point.SUBNASALE,)

    def test_tolerance_is_relative_to_scale(self):
        """La misma discrepancia en píxeles es aceptable en una foto
        grande e inaceptable en una pequeña. Por eso se normaliza."""
        pts = {Point.SUBNASALE: double(Point.SUBNASALE, (0.0, 0.0), (0.0, 5.0))}
        pts.update(frankfort_points())
        tight = MarkingSet(points=dict(pts), scale=40.0)   # 5/40 = 12,5 % → falla
        loose = MarkingSet(points=dict(pts), scale=200.0)  # 5/200 = 2,5 % → pasa
        assert tight.unreliable_points() == (Point.SUBNASALE,)
        assert loose.unreliable_points() == ()

    def test_single_marked_fragile_point_is_reported_as_flow_error(self):
        """Un punto frágil sin segunda pasada es un fallo del flujo de
        marcado, no un punto fiable. Hay que poder detectarlo."""
        pts = {Point.SUBNASALE: single(Point.SUBNASALE, 50.0, 60.0)}
        pts.update(frankfort_points())
        ms = MarkingSet(points=pts, scale=FRANKFORT_SCALE)
        assert ms.missing_double_marks() == (Point.SUBNASALE,)
        # y no aparece como "no fiable", porque no hay con qué juzgarlo
        assert ms.unreliable_points() == ()

    def test_rejects_non_positive_scale(self):
        with pytest.raises(ValueError, match="positiva"):
            MarkingSet(points={}, scale=0.0)


class TestErrorPropagation:
    def test_is_deterministic_for_a_given_seed(self, nasal_marking: MarkingSet):
        """Requisito de reproducibilidad: el mismo informe dos veces tiene
        que dar la misma banda."""
        spec = BY_NAME["goode_ratio"]
        a = propagate_error(spec, nasal_marking, seed=42)
        b = propagate_error(spec, nasal_marking, seed=42)
        assert a == b

    def test_different_seeds_give_similar_bands(self, nasal_marking: MarkingSet):
        """Si dos semillas dieran bandas muy distintas, el número de
        muestras sería insuficiente y la banda, ruido."""
        spec = BY_NAME["goode_ratio"]
        a = propagate_error(spec, nasal_marking, seed=1, samples=512)
        b = propagate_error(spec, nasal_marking, seed=2, samples=512)
        assert a == pytest.approx(b, rel=0.25)

    def test_band_grows_with_marking_dispersion(self):
        """El corazón del sistema: marcar peor tiene que ensanchar la
        banda. Si no creciera, la banda sería decorativa."""
        spec = BY_NAME["upper_third_pct"]

        def build(spread: float) -> MarkingSet:
            pts = {
                Point.TRICHION: double(Point.TRICHION, (50.0, -spread), (50.0, spread)),
                Point.GLABELLA: double(Point.GLABELLA, (50.0, 30 - spread), (50.0, 30 + spread)),
                Point.MENTON: double(Point.MENTON, (50.0, 90 - spread), (50.0, 90 + spread)),
            }
            pts.update(frankfort_points())
            return MarkingSet(points=pts, scale=FRANKFORT_SCALE)

        tight = propagate_error(spec, build(0.2), seed=7)
        loose = propagate_error(spec, build(1.5), seed=7)
        assert loose > tight * 2

    def test_capture_grade_widens_the_band(self, nasal_marking: MarkingSet):
        """El sello C es el selfie de gran angular. La distorsión no se
        puede corregir sin conocer la focal, así que se paga en banda."""
        spec = BY_NAME["goode_ratio"]
        bands = {}
        for grade in ("A", "B", "C"):
            ms = MarkingSet(
                points=nasal_marking.points,
                scale=nasal_marking.scale,
                capture_grade=grade,  # type: ignore[arg-type]
            )
            bands[grade] = propagate_error(spec, ms, seed=11)
        assert bands["A"] < bands["B"] < bands["C"]
        assert GRADE_FACTOR["C"] > GRADE_FACTOR["A"]

    def test_band_is_positive_and_finite(self, nasal_marking: MarkingSet):
        for name in ("goode_ratio", "nasolabial_angle", "nasofrontal_angle"):
            band = propagate_error(BY_NAME[name], nasal_marking, seed=3)
            assert band > 0
            assert math.isfinite(band)

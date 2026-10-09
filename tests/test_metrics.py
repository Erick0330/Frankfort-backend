"""Catálogo de métricas contra geometría de respuesta conocida."""

from __future__ import annotations

import numpy as np
import pytest

from frankfort.landmarks import Point
from frankfort.metrics import BY_NAME, REGISTRY, MissingPoints, metrics_depending_on
from frankfort.reliability import MarkedPoint, MarkingSet

from .conftest import FRANKFORT_SCALE, frankfort_points, p


class TestHardConstraints:
    """Las dos restricciones del §0 de la arquitectura, como tests."""

    def test_no_metric_reports_absolute_length(self):
        """Prohibido el milímetro.

        La fotogrametría 2D no da escala absoluta fiable, así que una
        métrica en mm sería un número inventado con aspecto de dato. La
        unidad está restringida por tipo, y esto lo verifica en runtime
        por si alguien amplía el Literal sin pensar.
        """
        allowed = {"deg", "ratio", "percent"}
        for m in REGISTRY:
            assert m.unit in allowed, f"{m.name} usa la unidad prohibida {m.unit}"

    def test_every_metric_declares_dependencies(self):
        """Sin `depends_on` no hay cascada, y la supresión se rompe en
        silencio: la métrica se reportaría siempre."""
        for m in REGISTRY:
            assert m.depends_on, f"{m.name} no declara dependencias"

    def test_no_metric_is_named_like_a_score(self):
        """Prohibido el score global de atractivo."""
        banned = ("score", "attractiveness", "beauty", "rating", "golden", "phi")
        for m in REGISTRY:
            for word in banned:
                assert word not in m.name.lower(), f"{m.name} suena a score"

    def test_reference_ranges_are_ordered(self):
        for m in REGISTRY:
            lo, hi = m.reference
            assert lo < hi, f"{m.name} tiene el rango de referencia invertido"


class TestVerticalThirds:
    def test_exact_thirds(self, thirds_marking: MarkingSet):
        pts = thirds_marking.consensus_map()
        for name in ("upper_third_pct", "middle_third_pct", "lower_third_pct"):
            assert BY_NAME[name].evaluate(pts) == pytest.approx(100 / 3)

    def test_thirds_sum_to_100(self, thirds_marking: MarkingSet):
        pts = thirds_marking.consensus_map()
        total = sum(
            BY_NAME[n].evaluate(pts)
            for n in ("upper_third_pct", "middle_third_pct", "lower_third_pct")
        )
        assert total == pytest.approx(100.0)

    def test_upper_third_does_not_depend_on_subnasale(self):
        """El reparto de dependencias que sostiene toda la sección
        "Lo que descartamos" de la landing.

        No es un detalle de implementación: es el motivo por el que un
        Subnasale mal marcado tumba dos tercios y deja uno en pie.
        """
        assert Point.SUBNASALE not in BY_NAME["upper_third_pct"].depends_on
        assert Point.SUBNASALE in BY_NAME["middle_third_pct"].depends_on
        assert Point.SUBNASALE in BY_NAME["lower_third_pct"].depends_on

    def test_subnasale_taints_exactly_two_thirds(self):
        affected = {m.name for m in metrics_depending_on(Point.SUBNASALE)}
        assert "middle_third_pct" in affected
        assert "lower_third_pct" in affected
        assert "upper_third_pct" not in affected


class TestNasalProfile:
    def test_goode_ratio_is_exactly_0575(self, nasal_marking: MarkingSet):
        got = BY_NAME["goode_ratio"].evaluate(nasal_marking.consensus_map())
        assert got == pytest.approx(0.575)

    def test_nasolabial_is_exactly_90(self, nasal_marking: MarkingSet):
        got = BY_NAME["nasolabial_angle"].evaluate(nasal_marking.consensus_map())
        assert got == pytest.approx(90.0)

    def test_goode_uses_horizontal_projection_not_straight_distance(
        self, nasal_marking: MarkingSet
    ):
        """El error clásico infla el Goode.

        La proyección va perpendicular a la vertical verdadera. Medida
        como distancia en línea recta desde el surco alar a la punta
        daría más, porque añade la componente vertical.
        """
        pts = nasal_marking.consensus_map()
        correct = BY_NAME["goode_ratio"].evaluate(pts)
        straight = float(
            np.linalg.norm(pts[Point.PRONASALE] - pts[Point.ALAR_CREASE])
        ) / 40.0
        assert straight > correct

    def test_goode_survives_head_tilt(self):
        """Con la cabeza inclinada, el Goode tiene que dar lo mismo.

        Es lo que compra la alineación a Frankfort. Si este test falla,
        la métrica está midiendo la pose del sujeto en vez de su nariz.
        """
        base = {
            Point.NASION: (52.0, 40.0),
            Point.PRONASALE: (76.0, 72.0),
            Point.ALAR_CREASE: (53.0, 74.0),
        }
        spec = BY_NAME["goode_ratio"]

        level_pts = {Point(k): p(*v) for k, v in base.items()}
        level_pts.update({k: v.consensus for k, v in frankfort_points(0.0).items()})
        level = spec.evaluate(level_pts)

        # Misma cara, girada 9° como un sólido rígido: puntos faciales y
        # plano de referencia juntos.
        from frankfort.geometry import rotate

        tilted_all = rotate(
            {k.value: v for k, v in level_pts.items()}, 9.0, about=p(10.0, 45.0)
        )
        tilted_pts = {Point(k): v for k, v in tilted_all.items()}
        tilted = spec.evaluate(tilted_pts)

        assert tilted == pytest.approx(level, abs=1e-9)


class TestMandibularPlane:
    def test_known_inclination(self, mandible_marking: MarkingSet):
        import math

        expected = abs(math.degrees(math.atan2(-20.0, 40.0)))
        got = BY_NAME["mandibular_plane_angle"].evaluate(
            mandible_marking.consensus_map()
        )
        assert got == pytest.approx(expected)

    def test_falls_inside_reference_range(self, mandible_marking: MarkingSet):
        spec = BY_NAME["mandibular_plane_angle"]
        got = spec.evaluate(mandible_marking.consensus_map())
        lo, hi = spec.reference
        assert lo <= got <= hi

    def test_reference_is_plane_angle_not_gonial(self):
        """Guarda contra volver a poner ~120°.

        Con Gonion, Menton, Porion y Orbitale lo que se puede medir es el
        ángulo del plano mandibular contra Frankfort (~22-28°). El ángulo
        gonial (~120-130°) necesita un punto de la rama mandibular que no
        está en el set. Ver docs/05-discrepancias.md.
        """
        lo, hi = BY_NAME["mandibular_plane_angle"].reference
        assert hi < 90, "un rango por encima de 90° sería el ángulo gonial"


class TestMissingPoints:
    def test_raises_with_the_names_of_what_falta(self, thirds_marking: MarkingSet):
        pts = dict(thirds_marking.consensus_map())
        del pts[Point.GLABELLA]
        with pytest.raises(MissingPoints) as exc:
            BY_NAME["upper_third_pct"].evaluate(pts)
        assert Point.GLABELLA in exc.value.missing

    def test_frankfort_metrics_require_the_reference_points(self):
        spec = BY_NAME["upper_third_pct"]
        pts = {
            Point.TRICHION: p(50, 0),
            Point.GLABELLA: p(50, 30),
            Point.MENTON: p(50, 90),
        }
        with pytest.raises(MissingPoints):
            spec.evaluate(pts)

"""El `metrology_auditor`: cascada, supresión y control cruzado."""

from __future__ import annotations

import pytest

from frankfort.auditor import (
    AuditReport,
    MetricResult,
    Status,
    SuppressionReason,
    audit_view,
    cross_check_profiles,
)
from frankfort.landmarks import Point, View
from frankfort.metrics import BY_NAME
from frankfort.reliability import MarkingSet

from .conftest import FRANKFORT_SCALE, double, frankfort_points, single


def result(report, name):
    return next(m for m in report.metrics if m.name == name)


class TestCascadeSuppression:
    """El caso real que cuenta la landing, ejecutado."""

    def test_bad_subnasale_suppresses_exactly_two_thirds(
        self, thirds_marking_bad_subnasale: MarkingSet
    ):
        rep = audit_view(thirds_marking_bad_subnasale, View.PROFILE_RIGHT, samples=256)

        upper = result(rep, "upper_third_pct")
        middle = result(rep, "middle_third_pct")
        lower = result(rep, "lower_third_pct")

        assert upper.status is Status.REPORTED
        assert middle.status is Status.SUPPRESSED
        assert lower.status is Status.SUPPRESSED
        assert middle.reason is SuppressionReason.UNRELIABLE_DEPENDENCY
        assert lower.reason is SuppressionReason.UNRELIABLE_DEPENDENCY

    def test_one_of_three_thirds_survives(self, thirds_marking_bad_subnasale: MarkingSet):
        """La frase que la landing pone bajo el diagrama, como aserción."""
        rep = audit_view(thirds_marking_bad_subnasale, View.PROFILE_RIGHT, samples=256)
        thirds = [m for m in rep.metrics if m.name.endswith("_third_pct")]
        survivors = [m for m in thirds if m.status is Status.REPORTED]
        assert len(thirds) == 3
        assert len(survivors) == 1
        assert survivors[0].name == "upper_third_pct"

    def test_suppression_names_the_culprit(self, thirds_marking_bad_subnasale: MarkingSet):
        """No basta con suprimir: hay que decir por qué y por culpa de qué.
        Es lo que se publica en la sección de descartes."""
        rep = audit_view(thirds_marking_bad_subnasale, View.PROFILE_RIGHT, samples=256)
        middle = result(rep, "middle_third_pct")
        assert "subnasale" in middle.detail.lower()

    def test_unreliable_points_listed_in_the_report(
        self, thirds_marking_bad_subnasale: MarkingSet
    ):
        rep = audit_view(thirds_marking_bad_subnasale, View.PROFILE_RIGHT, samples=256)
        assert rep.unreliable_points == (Point.SUBNASALE,)

    def test_clean_marking_suppresses_nothing_by_cascade(self, thirds_marking: MarkingSet):
        rep = audit_view(thirds_marking, View.PROFILE_RIGHT, samples=256)
        cascaded = [
            m for m in rep.metrics if m.reason is SuppressionReason.UNRELIABLE_DEPENDENCY
        ]
        assert cascaded == []


class TestBandVersusDeviation:
    def test_value_inside_reference_is_reported(self, thirds_marking: MarkingSet):
        """Un valor dentro del rango no tiene hallazgo que sostener, así
        que se reporta sin más. La supresión es para desviaciones que no
        se distinguen del ruido, no para valores normales."""
        rep = audit_view(thirds_marking, View.PROFILE_RIGHT, samples=256)
        upper = result(rep, "upper_third_pct")
        assert upper.status is Status.REPORTED
        assert upper.deviation == 0.0
        assert not upper.is_finding

    def test_noisy_deviation_is_suppressed(self):
        """Valor fuera de rango pero con banda más ancha que la
        desviación: no se puede afirmar nada.

        La dispersión hay que calibrarla con cuidado: tiene que ensanchar
        la banda SIN cruzar la tolerancia del punto, porque si la cruza
        salta primero la cascada y el test acabaría comprobando el otro
        mecanismo. 2,5 sobre escala 60 = 4,2 %, por debajo del 6 %.
        El ensanchamiento lo aporta el sello de captura C (×2,5).

        Tercio superior en 27 % (fuera de 30–36 por 3 puntos) con una
        banda de ~5, que se lo come.
        """
        pts = {
            Point.TRICHION: double(Point.TRICHION, (50.0, -1.25), (50.0, 1.25)),
            Point.GLABELLA: double(Point.GLABELLA, (50.0, 25.75), (50.0, 28.25)),
            Point.MENTON: double(Point.MENTON, (50.0, 98.75), (50.0, 101.25)),
        }
        pts.update(frankfort_points())
        ms = MarkingSet(points=pts, scale=FRANKFORT_SCALE, capture_grade="C")

        # Ningún punto debe haber cruzado la tolerancia: si esto falla, el
        # test ya no mide lo que dice medir.
        assert ms.unreliable_points() == ()

        rep = audit_view(ms, View.PROFILE_RIGHT, samples=512)
        upper = result(rep, "upper_third_pct")
        assert upper.value == pytest.approx(27.0)
        assert upper.status is Status.SUPPRESSED
        assert upper.reason is SuppressionReason.BAND_EXCEEDS_DEVIATION
        assert upper.error_band is not None and upper.error_band >= upper.deviation

    def test_clear_deviation_with_tight_band_becomes_a_finding(self):
        """Y al contrario: desviación grande con marcado preciso SÍ es un
        hallazgo. Si esto no pasara, el sistema no reportaría nada nunca."""
        # Tercio inferior claramente largo, marcado muy preciso
        pts = {
            Point.TRICHION: double(Point.TRICHION, (50.0, -0.05), (50.0, 0.05)),
            Point.GLABELLA: double(Point.GLABELLA, (50.0, 24.95), (50.0, 25.05)),
            Point.SUBNASALE: double(Point.SUBNASALE, (50.0, 49.95), (50.0, 50.05)),
            Point.MENTON: double(Point.MENTON, (50.0, 99.95), (50.0, 100.05)),
        }
        pts.update(frankfort_points())
        ms = MarkingSet(points=pts, scale=FRANKFORT_SCALE, capture_grade="A")
        rep = audit_view(ms, View.PROFILE_RIGHT, samples=512)
        lower = result(rep, "lower_third_pct")
        assert lower.value == pytest.approx(50.0)
        assert lower.status is Status.REPORTED
        assert lower.is_finding
        assert lower.deviation == pytest.approx(14.0)


class TestNotComputable:
    def test_missing_points_are_not_computable_not_suppressed(self):
        """Distinción que importa: "no lo medimos" no es lo mismo que
        "lo medimos y no aguantó"."""
        pts = {Point.TRICHION: double(Point.TRICHION, (50.0, 0.0), (50.0, 0.0))}
        pts.update(frankfort_points())
        ms = MarkingSet(points=pts, scale=FRANKFORT_SCALE)
        rep = audit_view(ms, View.PROFILE_RIGHT, samples=64)
        upper = result(rep, "upper_third_pct")
        assert upper.status is Status.NOT_COMPUTABLE
        assert upper.reason is SuppressionReason.MISSING_POINTS
        assert upper not in rep.suppressed


class TestCrossCheckVerdicts:
    """La clasificación, en aislamiento.

    Se construyen los `AuditReport` a mano en vez de hacerlos pasar por el
    Monte Carlo. Motivo: la banda que sale de la propagación depende de la
    geometría de la fixture de forma poco intuitiva, y calibrarla para
    caer en cada rama daría tests que se rompen al tocar cualquier
    constante. Aquí las bandas son las del enunciado, y lo que se prueba
    es la decisión — que es lo que el test dice probar.

    La integración por la tubería real la cubren los tests de abajo.
    """

    @staticmethod
    def _report(value: float, band: float) -> AuditReport:
        return AuditReport(
            metrics=[
                MetricResult(
                    name="nasolabial_angle",
                    unit="deg",
                    status=Status.REPORTED,
                    value=value,
                    error_band=band,
                    reference=(90.0, 110.0),
                    depends_on=BY_NAME["nasolabial_angle"].depends_on,
                )
            ]
        )

    def _verdict(self, r: tuple[float, float], l: tuple[float, float]):
        checks = cross_check_profiles(self._report(*r), self._report(*l))
        assert len(checks) == 1
        return checks[0]

    def test_difference_within_combined_bands_is_concordant(self):
        # 4° de diferencia, ±3 y ±3 → 6 combinados. Cabe.
        c = self._verdict((96.0, 3.0), (100.0, 3.0))
        assert c.verdict == "concordant"
        assert "sólido" in c.detail

    def test_precise_and_divergent_is_real_asymmetry(self):
        """Los dos lados medidos con precisión y aun así distintos: eso es
        asimetría, y hay que decirlo así.

        20° de diferencia con ±1 y ±1,5: los dos lados son al menos 3×
        más precisos que la propia discrepancia.
        """
        c = self._verdict((95.0, 1.0), (75.0, 1.5))
        assert c.verdict == "real_asymmetry"
        assert c.difference == pytest.approx(20.0)

    def test_one_imprecise_side_is_measurement_error(self):
        """Discrepan, pero un lado se midió tan mal que no hay derecho a
        afirmar asimetría. El sistema pide volver a marcar.

        20° de diferencia, pero la banda del lado izquierdo (±9) no es 3×
        menor que 20. Sobra imprecisión, no falta simetría.
        """
        c = self._verdict((95.0, 1.0), (75.0, 9.0))
        assert c.verdict == "measurement_error"
        assert "volver a marcar" in c.detail

    def test_both_imprecise_is_measurement_error(self):
        c = self._verdict((95.0, 8.0), (75.0, 9.0))
        assert c.verdict == "measurement_error"

    def test_boundary_exactly_at_combined_band_is_concordant(self):
        """En el límite se elige concordante: afirmar asimetría exige
        superar la banda, no igualarla."""
        c = self._verdict((90.0, 2.0), (94.0, 2.0))
        assert c.difference == pytest.approx(c.combined_band)
        assert c.verdict == "concordant"


class TestCrossCheckIntegration:
    def test_concordant_through_the_real_pipeline(self):
        """Un caso end-to-end: dos perfiles medidos limpiamente y con
        valores casi iguales tienen que salir concordantes."""

        def profile(offset: float) -> MarkingSet:
            pts = {
                Point.SUBNASALE: double(
                    Point.SUBNASALE, (50.0, 59.85), (50.0, 60.15)
                ),
                Point.COLUMELLA_APEX: single(Point.COLUMELLA_APEX, 60.0, 50.0 + offset),
                Point.LABRALE_SUPERIUS: single(Point.LABRALE_SUPERIUS, 40.0, 50.0),
            }
            pts.update(frankfort_points())
            return MarkingSet(points=pts, scale=FRANKFORT_SCALE)

        right = audit_view(profile(0.0), View.PROFILE_RIGHT, samples=256)
        left = audit_view(profile(0.2), View.PROFILE_LEFT, samples=256)
        checks = cross_check_profiles(right, left)
        nl = next(c for c in checks if c.metric == "nasolabial_angle")
        assert nl.verdict == "concordant"

    def test_only_compares_metrics_reported_on_both_sides(
        self, thirds_marking: MarkingSet, thirds_marking_bad_subnasale: MarkingSet
    ):
        """Si un lado suprimió una métrica, no hay nada que cruzar."""
        right = audit_view(thirds_marking, View.PROFILE_RIGHT, samples=256)
        left = audit_view(thirds_marking_bad_subnasale, View.PROFILE_LEFT, samples=256)
        names = {c.metric for c in cross_check_profiles(right, left)}
        assert "middle_third_pct" not in names
        assert "upper_third_pct" in names


class TestReportShape:
    def test_partitions_are_disjoint_and_complete(self, thirds_marking: MarkingSet):
        rep = audit_view(thirds_marking, View.PROFILE_RIGHT, samples=128)
        total = len(rep.reported) + len(rep.suppressed)
        not_computable = [m for m in rep.metrics if m.status is Status.NOT_COMPUTABLE]
        assert total + len(not_computable) == len(rep.metrics)

    def test_findings_are_a_subset_of_reported(self, thirds_marking: MarkingSet):
        rep = audit_view(thirds_marking, View.PROFILE_RIGHT, samples=128)
        assert all(f in rep.reported for f in rep.findings)

    def test_only_metrics_for_the_requested_view(self, nasal_marking: MarkingSet):
        rep = audit_view(nasal_marking, View.FRONTAL_REST, samples=64)
        names = {m.name for m in rep.metrics}
        # goode y nasolabial son de perfil; no deben aparecer en frontal
        assert "goode_ratio" not in names
        assert "nasolabial_angle" not in names

    def test_every_result_carries_its_dependencies(self, thirds_marking: MarkingSet):
        """Procedencia adjunta, del §0: nada sale sin decir de qué depende."""
        rep = audit_view(thirds_marking, View.PROFILE_RIGHT, samples=64)
        for m in rep.metrics:
            assert m.depends_on == BY_NAME[m.name].depends_on
            assert m.depends_on

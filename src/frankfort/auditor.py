"""El `metrology_auditor`. La parte determinista, que es la que decide.

Es el nodo que nadie más tiene, y no lleva LLM dentro a propósito: la
decisión de suprimir una métrica tiene que ser reproducible y auditable,
no producto del criterio de un modelo que puede olvidarse.

Tres mecanismos, en orden de dureza:

1. **Cascada por dependencia.** Un punto frágil cuyas dos marcas no
   coinciden se declara no fiable, y TODA métrica que lo declare en
   `depends_on` queda suprimida. Sin excepciones y sin que nadie tenga
   que acordarse: se sigue el grafo.

2. **Banda contra desviación.** Si el valor cae fuera del rango de
   referencia pero la banda de error es igual o mayor que esa desviación,
   la métrica no puede distinguir señal de error de marcado. Se suprime.
   Un valor DENTRO del rango sí se reporta: no hay hallazgo que sostener.

3. **Control cruzado entre perfiles.** La misma métrica medida en los dos
   lados. Si discrepan más que sus bandas combinadas, hay que decir de
   qué se trata: asimetría real (ambos lados medidos con precisión) o
   error de medición (al menos un lado impreciso).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from .landmarks import Point, View
from .metrics import REGISTRY, MetricSpec, MissingPoints
from .reliability import MarkingSet, propagate_error


class Status(StrEnum):
    REPORTED = "reported"
    SUPPRESSED = "suppressed"
    NOT_COMPUTABLE = "not_computable"


class SuppressionReason(StrEnum):
    UNRELIABLE_DEPENDENCY = "unreliable_dependency"
    BAND_EXCEEDS_DEVIATION = "band_exceeds_deviation"
    MISSING_POINTS = "missing_points"
    COMPUTE_FAILED = "compute_failed"


@dataclass(frozen=True, slots=True)
class MetricResult:
    name: str
    unit: str
    status: Status
    value: float | None = None
    error_band: float | None = None
    #: Cuánto se sale del rango de referencia. 0.0 si cae dentro.
    deviation: float = 0.0
    reference: tuple[float, float] | None = None
    depends_on: tuple[Point, ...] = ()
    reason: SuppressionReason | None = None
    #: Explicación en prosa, apta para el informe. En español: la
    #: traducción al inglés la hace el nodo `explainer`, no este.
    detail: str = ""

    @property
    def is_finding(self) -> bool:
        """Reportada Y fuera del rango de referencia."""
        return self.status is Status.REPORTED and self.deviation > 0.0


@dataclass(frozen=True, slots=True)
class CrossCheck:
    metric: str
    right: float
    left: float
    difference: float
    combined_band: float
    verdict: Literal["concordant", "real_asymmetry", "measurement_error"]
    detail: str


@dataclass(slots=True)
class AuditReport:
    metrics: list[MetricResult] = field(default_factory=list)
    cross_checks: list[CrossCheck] = field(default_factory=list)
    unreliable_points: tuple[Point, ...] = ()
    missing_double_marks: tuple[Point, ...] = ()

    @property
    def reported(self) -> list[MetricResult]:
        return [m for m in self.metrics if m.status is Status.REPORTED]

    @property
    def suppressed(self) -> list[MetricResult]:
        return [m for m in self.metrics if m.status is Status.SUPPRESSED]

    @property
    def findings(self) -> list[MetricResult]:
        return [m for m in self.metrics if m.is_finding]


def _deviation_from_reference(value: float, reference: tuple[float, float]) -> float:
    lo, hi = reference
    if value < lo:
        return lo - value
    if value > hi:
        return value - hi
    return 0.0


def _fmt(value: float, unit: str) -> str:
    if unit == "deg":
        return f"{value:.1f}°"
    if unit == "percent":
        return f"{value:.1f} %"
    return f"{value:.3f}"


def audit_view(
    marking: MarkingSet,
    view: View,
    *,
    specs: tuple[MetricSpec, ...] = REGISTRY,
    samples: int = 512,
    seed: int = 0,
) -> AuditReport:
    """Audita todas las métricas aplicables a una vista."""
    unreliable = set(marking.unreliable_points())
    report = AuditReport(
        unreliable_points=marking.unreliable_points(),
        missing_double_marks=marking.missing_double_marks(),
    )

    for spec in specs:
        if view not in spec.views:
            continue

        # ── Mecanismo 1: cascada por dependencia ──
        tainted = tuple(sorted((p for p in spec.depends_on if p in unreliable), key=lambda x: x.value))
        if tainted:
            names = ", ".join(p.value for p in tainted)
            report.metrics.append(
                MetricResult(
                    name=spec.name,
                    unit=spec.unit,
                    status=Status.SUPPRESSED,
                    reference=spec.reference,
                    depends_on=spec.depends_on,
                    reason=SuppressionReason.UNRELIABLE_DEPENDENCY,
                    detail=(
                        f"Suprimida: depende de {names}, cuyas dos marcas "
                        f"discreparon más de la tolerancia. El valor no se "
                        f"reporta porque no se puede separar del error de marcado."
                    ),
                )
            )
            continue

        # ── Cálculo ──
        try:
            value = spec.evaluate(marking.consensus_map())
        except MissingPoints as exc:
            report.metrics.append(
                MetricResult(
                    name=spec.name,
                    unit=spec.unit,
                    status=Status.NOT_COMPUTABLE,
                    reference=spec.reference,
                    depends_on=spec.depends_on,
                    reason=SuppressionReason.MISSING_POINTS,
                    detail=f"No calculable: faltan {[p.value for p in exc.missing]}.",
                )
            )
            continue
        except (ValueError, ZeroDivisionError) as exc:
            report.metrics.append(
                MetricResult(
                    name=spec.name,
                    unit=spec.unit,
                    status=Status.NOT_COMPUTABLE,
                    reference=spec.reference,
                    depends_on=spec.depends_on,
                    reason=SuppressionReason.COMPUTE_FAILED,
                    detail=f"No calculable: {exc}",
                )
            )
            continue

        band = propagate_error(spec, marking, samples=samples, seed=seed)
        deviation = _deviation_from_reference(value, spec.reference)

        # ── Mecanismo 2: banda contra desviación ──
        if deviation > 0.0 and band >= deviation:
            report.metrics.append(
                MetricResult(
                    name=spec.name,
                    unit=spec.unit,
                    status=Status.SUPPRESSED,
                    value=value,
                    error_band=band,
                    deviation=deviation,
                    reference=spec.reference,
                    depends_on=spec.depends_on,
                    reason=SuppressionReason.BAND_EXCEEDS_DEVIATION,
                    detail=(
                        f"Suprimida: {_fmt(value, spec.unit)} se sale del rango "
                        f"de referencia en {_fmt(deviation, spec.unit)}, pero la "
                        f"banda de error es de {_fmt(band, spec.unit)}. La "
                        f"desviación no se distingue del ruido de medición."
                    ),
                )
            )
            continue

        inside = deviation == 0.0
        report.metrics.append(
            MetricResult(
                name=spec.name,
                unit=spec.unit,
                status=Status.REPORTED,
                value=value,
                error_band=band,
                deviation=deviation,
                reference=spec.reference,
                depends_on=spec.depends_on,
                detail=(
                    f"{_fmt(value, spec.unit)} ± {_fmt(band, spec.unit)} — "
                    + (
                        "dentro del rango de referencia "
                        f"({_fmt(spec.reference[0], spec.unit)}–{_fmt(spec.reference[1], spec.unit)})."
                        if inside
                        else f"fuera del rango de referencia en {_fmt(deviation, spec.unit)}."
                    )
                ),
            )
        )

    return report


def cross_check_profiles(
    right: AuditReport,
    left: AuditReport,
    *,
    precision_factor: float = 3.0,
) -> list[CrossCheck]:
    """Compara la misma métrica medida en los dos perfiles.

    `precision_factor`: para llamar asimetría real a una discrepancia, la
    banda de CADA lado tiene que ser al menos este factor más pequeña que
    la propia discrepancia. Si no, lo que sobra es imprecisión y no hay
    derecho a afirmar asimetría.
    """
    by_name_r = {m.name: m for m in right.reported}
    by_name_l = {m.name: m for m in left.reported}
    out: list[CrossCheck] = []

    for name in sorted(set(by_name_r) & set(by_name_l)):
        r, l = by_name_r[name], by_name_l[name]
        if r.value is None or l.value is None:
            continue
        br = r.error_band or 0.0
        bl = l.error_band or 0.0
        diff = abs(r.value - l.value)
        combined = br + bl

        if diff <= combined:
            verdict: Literal["concordant", "real_asymmetry", "measurement_error"] = "concordant"
            detail = (
                f"Los dos lados coinciden dentro de sus bandas "
                f"({_fmt(diff, r.unit)} de diferencia, {_fmt(combined, r.unit)} combinados). "
                f"El hallazgo es sólido."
            )
        elif br * precision_factor <= diff and bl * precision_factor <= diff:
            verdict = "real_asymmetry"
            detail = (
                f"Discrepan {_fmt(diff, r.unit)}, y los dos lados se midieron con "
                f"precisión suficiente (±{_fmt(br, r.unit)} y ±{_fmt(bl, r.unit)}). "
                f"Es asimetría real, no error."
            )
        else:
            verdict = "measurement_error"
            detail = (
                f"Discrepan {_fmt(diff, r.unit)}, pero al menos un lado se midió "
                f"con poca precisión (±{_fmt(br, r.unit)} y ±{_fmt(bl, r.unit)}). "
                f"Antes de hablar de asimetría hay que volver a marcar."
            )

        out.append(
            CrossCheck(
                metric=name,
                right=r.value,
                left=l.value,
                difference=diff,
                combined_band=combined,
                verdict=verdict,
                detail=detail,
            )
        )

    return out

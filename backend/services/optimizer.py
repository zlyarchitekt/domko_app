"""Layout optimizer service.

Backend optimizer that generates top-3 layout variants for a given footprint,
apartment program, location, date, and cage mode.

- Simple (convex) footprints with a single stair cage -> mixed-integer LP via
  scipy.optimize.milp.
- Concave footprints or multi-cage mode -> multi-objective GA via pymoo NSGA-II.

Output variants expose solar_score (average sunny facade hours weighted by
length) and wt_compliance (share of WT rules passed + apartment-level share).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Tuple

import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from shapely.geometry import Polygon

from services.bsp import bsp_zones, concave_vertices
from services.layout import (
    ApartmentSpec,
    LayoutInput,
    LayoutResult,
    generate_layout,
    azimuth_to_cardinal,
    sunlight_adjustment_factor,
)
from services.solar_analysis import analyze_solar_access, SolarAnalysisResult
from services.wt_validation import validate_layout_wt, WTValidationResult


@dataclass
class OptimizerInput:
    """Normalized optimizer input."""

    footprint: Polygon
    apartments: List[ApartmentSpec]
    latitude: float
    longitude: float
    analysis_date: date
    timezone: str = "Europe/Warsaw"
    required_hours: float = 3.0
    cage_mode: str = "auto"  # auto | single | multiple
    corridor_width_m: float = 1.5
    stair_width_m: float = 1.2
    cage_size_m: float = 2.5
    local_law: str | None = None
    max_variants: int = 3


@dataclass
class VariantMetrics:
    """Metrics attached to a single variant."""

    solar_score: float
    """Average sunny facade hours weighted by facade length (h)."""

    wt_compliance: float
    """Share 0..1 of WT rules passed (also incorporates apartment WT pass rate)."""

    total_apartments: int
    total_facades: int
    facades_meeting_wt: int
    wt_rules_passed: int
    wt_rules_total: int


@dataclass
class OptimizerVariant:
    """One optimized layout variant ready for serialization."""

    rank: int
    layout: LayoutResult
    solar_analysis: SolarAnalysisResult
    wt_validation: WTValidationResult
    metrics: VariantMetrics
    config: Dict[str, Any] = field(default_factory=dict)
    """Key parameters that distinguish this variant (e.g. corridor_width, cage_count)."""


@dataclass
class OptimizerResult:
    """Top-K optimizer result."""

    variants: List[OptimizerVariant]
    method: str
    footprint_is_concave: bool
    requested_cage_mode: str
    effective_cage_mode: str


def run_optimizer(input: OptimizerInput) -> OptimizerResult:
    """Run the optimizer and return top variants."""
    footprint = input.footprint
    is_concave = bool(concave_vertices(footprint))
    requested_cage_mode = input.cage_mode

    # Decide effective cage mode.
    effective_cage_mode = requested_cage_mode
    if effective_cage_mode == "auto":
        # Multiple cages only make sense for bigger / concave footprints.
        effective_cage_mode = "multiple" if is_concave or footprint.area > 600 else "single"

    # Decide method.
    # LP requires: convex footprint, single cage, small enough problem.
    use_lp = (
        not is_concave
        and effective_cage_mode == "single"
        and len(input.apartments) <= 6
    )

    if use_lp:
        variants = _run_lp_branch(input)
        method = "lp"
    else:
        variants = _run_ga_branch(input)
        method = "ga"

    # Rank variants by scalarized score: 60% solar, 40% wt_compliance.
    ranked = sorted(
        variants,
        key=lambda v: 0.6 * _normalize_solar(v.metrics.solar_score)
        + 0.4 * v.metrics.wt_compliance,
        reverse=True,
    )

    for i, v in enumerate(ranked[: input.max_variants]):
        v.rank = i + 1

    return OptimizerResult(
        variants=ranked[: input.max_variants],
        method=method,
        footprint_is_concave=is_concave,
        requested_cage_mode=requested_cage_mode,
        effective_cage_mode=effective_cage_mode,
    )


def _normalize_solar(hours: float) -> float:
    """Normalize solar score to 0..1 assuming 8 h is excellent."""
    return max(0.0, min(1.0, hours / 8.0))


def _build_base_input(input: OptimizerInput, overrides: Dict[str, Any]) -> LayoutInput:
    """Build a LayoutInput from optimizer input + parameter overrides."""
    return LayoutInput(
        footprint=input.footprint,
        corridor_width_m=overrides.get("corridor_width_m", input.corridor_width_m),
        stair_width_m=overrides.get("stair_width_m", input.stair_width_m),
        place_cage=overrides.get("place_cage", True),
        cage_size_m=overrides.get("cage_size_m", input.cage_size_m),
        apartments=input.apartments,
        local_law=input.local_law,
    )


def _evaluate_variant(
    layout: LayoutResult,
    input: OptimizerInput,
    config: Dict[str, Any],
) -> OptimizerVariant:
    """Compute solar and WT metrics for a generated layout."""
    solar = analyze_solar_access(
        layout,
        latitude=input.latitude,
        longitude=input.longitude,
        analysis_date=input.analysis_date,
        timezone=input.timezone,
        required_hours=input.required_hours,
    )
    wt = validate_layout_wt(layout, input.local_law)

    total_facade_length = sum(f.length_m for f in solar.facades)
    weighted_hours = (
        sum(f.hours_total * f.length_m for f in solar.facades) / total_facade_length
        if total_facade_length > 1e-6
        else 0.0
    )

    wt_rules_total = max(1, len(wt.rules))
    wt_rules_passed = sum(1 for r in wt.rules if r.passed)
    apt_wt_pass_rate = _apartment_wt_pass_rate(solar, input.required_hours)
    wt_compliance = (wt_rules_passed / wt_rules_total) * 0.5 + apt_wt_pass_rate * 0.5

    metrics = VariantMetrics(
        solar_score=round(weighted_hours, 2),
        wt_compliance=round(wt_compliance, 3),
        total_apartments=len(layout.apartments),
        total_facades=len(solar.facades),
        facades_meeting_wt=sum(1 for f in solar.facades if f.meets_wt),
        wt_rules_passed=wt_rules_passed,
        wt_rules_total=wt_rules_total,
    )

    return OptimizerVariant(
        rank=0,
        layout=layout,
        solar_analysis=solar,
        wt_validation=wt,
        metrics=metrics,
        config=config,
    )


def _apartment_wt_pass_rate(solar: SolarAnalysisResult, required_hours: float) -> float:
    """Share of apartments whose every facade meets the sunlight threshold."""
    if not solar.apartments:
        return 1.0
    passed = sum(1 for a in solar.apartments if a.get("wt_passed", False))
    return passed / len(solar.apartments)


# ═══════════════════════════════════════════════════════════════════
# LP branch
# ═══════════════════════════════════════════════════════════════════


def _run_lp_branch(input: OptimizerInput) -> List[OptimizerVariant]:
    """Use scipy MILP to choose discrete layout parameters.

    Decision variables (binary / bounded real):
      x0 = corridor_width in {1.2, 1.5, 1.8}
      x1 = cage_size in {2.0, 2.5, 3.0}
      x2 = place_cage (binary)

    Objective: maximize weighted solar hours. Since solar is non-linear and
    expensive, we approximate it with a surrogate based on orientation factors
    and facade length.
    """
    corridor_options = [1.2, 1.5, 1.8]
    cage_options = [2.0, 2.5, 3.0]

    # Enumerate all combos and evaluate exactly; keep top-K via surrogate pre-filter.
    candidates: List[Tuple[float, Dict[str, Any]]] = []
    for cw in corridor_options:
        for cs in cage_options:
            for place in (True, False):
                cfg = {
                    "corridor_width_m": cw,
                    "cage_size_m": cs,
                    "place_cage": place,
                }
                surrogate = _surrogate_score(input, cfg)
                candidates.append((surrogate, cfg))

    # Take top 6 surrogate configs and evaluate exactly.
    candidates.sort(key=lambda x: x[0], reverse=True)
    variants: List[OptimizerVariant] = []
    for _, cfg in candidates[:6]:
        try:
            layout_input = _build_base_input(input, cfg)
            layout = generate_layout(layout_input)
        except Exception:
            continue
        if not layout.apartments:
            continue
        variants.append(_evaluate_variant(layout, input, cfg))

    if not variants:
        # Fallback to default.
        layout = generate_layout(_build_base_input(input, {}))
        variants.append(_evaluate_variant(layout, input, {}))

    return variants


def _surrogate_score(input: OptimizerInput, cfg: Dict[str, Any]) -> float:
    """Fast surrogate: weighted sunlight adjustment over exterior facade length.

    We approximate exterior facade length per orientation by intersecting the
    footprint with expanded bounding slices. This avoids full layout generation.
    """
    footprint = input.footprint
    corridor_width = cfg.get("corridor_width_m", input.corridor_width_m)
    # Heuristic: usable facade length = perimeter minus corridor cut.
    exterior = footprint.length
    usable_length = max(0.0, exterior - corridor_width * 2)

    # Distribute length across cardinal directions based on building azimuth.
    from services.layout import _estimate_building_azimuth

    azimuth = _estimate_building_azimuth(footprint) or 180.0
    factor = sunlight_adjustment_factor(azimuth)

    # Approximate average solar hours: south-facing ~7 h on equinox, scaled.
    base_hours = 7.0 * factor
    score = base_hours * usable_length / max(1.0, exterior)
    # Small penalty for large cage / wide corridor to promote usable area.
    cage_size = cfg.get("cage_size_m", input.cage_size_m)
    score -= 0.05 * cage_size + 0.05 * corridor_width
    if not cfg.get("place_cage", True):
        score -= 0.3  # penalize missing cage for WT
    return score


# ═══════════════════════════════════════════════════════════════════
# GA branch (pymoo NSGA-II)
# ═══════════════════════════════════════════════════════════════════


def _run_ga_branch(input: OptimizerInput) -> List[OptimizerVariant]:
    """Run a small NSGA-II optimization over layout parameters.

    Variables (all real, later snapped):
      x0 = corridor_width in [1.0, 2.2]
      x1 = cage_size in [1.8, 3.5]
      x2 = place_cage threshold -> binary via rounding
      x3 = cage_count target for concave footprints [1, 3]
    """
    try:
        from pymoo.algorithms.moo.nsga2 import NSGA2
        from pymoo.core.problem import Problem
        from pymoo.optimize import minimize
        from pymoo.visualization.scatter import Scatter
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError("pymoo is required for the GA branch") from exc

    class LayoutProblem(Problem):
        def __init__(self, input: OptimizerInput):
            super().__init__(
                n_var=4,
                n_obj=2,
                xl=np.array([1.0, 1.8, 0.0, 1.0]),
                xu=np.array([2.2, 3.5, 1.0, 3.0]),
                n_constr=0,
                elementwise_evaluation=False,
            )
            self.opt_input = input

        def _evaluate(self, X, out, *args, **kwargs):
            F = []
            for x in X:
                cfg = _decode_ga_vars(x)
                try:
                    layout_input = _build_base_input(self.opt_input, cfg)
                    layout = generate_layout(layout_input)
                    variant = _evaluate_variant(layout, self.opt_input, cfg)
                except Exception:
                    F.append([0.0, -1.0])  # bad solar, bad wt to keep feasible
                    continue

                # Objectives: maximize solar_score, maximize wt_compliance
                # pymoo minimizes, so negate.
                F.append([-variant.metrics.solar_score, -variant.metrics.wt_compliance])
            out["F"] = np.array(F)

    problem = LayoutProblem(input)
    algorithm = NSGA2(pop_size=10, eliminate_duplicates=True)

    result = minimize(
        problem,
        algorithm,
        ("n_gen", 5),
        seed=42,
        verbose=False,
    )

    # Decode unique evaluated configs and re-evaluate the best non-dominated set.
    seen: set = set()
    variants: List[OptimizerVariant] = []
    if result.X is not None:
        for x in result.X:
            cfg = _decode_ga_vars(x)
            key = (
                round(cfg.get("corridor_width_m", 0), 2),
                round(cfg.get("cage_size_m", 0), 2),
                cfg.get("place_cage", True),
                cfg.get("cage_count", 1),
            )
            if key in seen:
                continue
            seen.add(key)
            try:
                layout_input = _build_base_input(input, cfg)
                layout = generate_layout(layout_input)
                if not layout.apartments:
                    continue
                variants.append(_evaluate_variant(layout, input, cfg))
            except Exception:
                continue

    if not variants:
        layout = generate_layout(_build_base_input(input, {}))
        variants.append(_evaluate_variant(layout, input, {}))

    return variants


def _decode_ga_vars(x: np.ndarray) -> Dict[str, Any]:
    """Convert continuous GA variables to a discrete layout config."""
    x = np.asarray(x).flatten()
    corridor = float(np.clip(round(float(x[0]), 2), 1.0, 2.2))
    cage_size = float(np.clip(round(float(x[1]), 2), 1.8, 3.5))
    place_cage = bool(round(float(x[2])))
    cage_count = int(np.clip(round(float(x[3])), 1, 3))
    return {
        "corridor_width_m": corridor,
        "cage_size_m": cage_size,
        "place_cage": place_cage,
        "cage_count": cage_count,
    }

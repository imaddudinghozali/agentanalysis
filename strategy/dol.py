from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .common import Candle, StrategyConfig, average_true_range, confidence_from_score
from .displacement import DisplacementSignal
from .liquidity import LiquidityPool, SweepEvent
from .range import DealingRange
from .ssmt import SSMTSignal
from .structure import StructureSignal


@dataclass(frozen=True)
class DOLCandidate:
    label: str
    timeframe: str
    liquidity_type: str
    direction: str
    price: float
    score: int
    confidence: str
    reasoning: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DOLSelection:
    selected: DOLCandidate | None
    candidates: list[DOLCandidate]
    ambiguous: bool = False
    reason_code: str | None = None


def score_dol_candidates(
    pools: Sequence[LiquidityPool],
    active_range: DealingRange | None,
    m15_candles: Sequence[Candle],
    sweeps: Sequence[SweepEvent],
    displacement: DisplacementSignal,
    structure: StructureSignal,
    ssmt: SSMTSignal,
    time_context: object,
    config: StrategyConfig,
    htf_direction: str | None = None,
    direction_hierarchy: object | None = None,
    hrlr_lrlr: object | None = None,
    mmxm_grade: object | None = None,
    judas_swing: object | None = None,
    nine_am_model: object | None = None,
    include_execution_factors: bool = False,
    prefer_actionable_targets: bool = False,
) -> DOLSelection:
    if active_range is None or not m15_candles:
        return DOLSelection(None, [], reason_code="NO_ACTIVE_DEALING_RANGE")
    if htf_direction in (None, "neutral"):
        return DOLSelection(None, [], reason_code="UNCLEAR_DOL")
    current_price = m15_candles[-1].close
    atr = average_true_range(m15_candles) or max(abs(active_range.high - active_range.low) / 20.0, 0.01)
    candidates = [
        _score_pool(
            pool,
            active_range,
            current_price,
            atr,
            sweeps,
            displacement,
            structure,
            ssmt,
            time_context,
            htf_direction,
            direction_hierarchy,
            hrlr_lrlr,
            mmxm_grade,
            judas_swing,
            nine_am_model,
            include_execution_factors,
            prefer_actionable_targets,
        )
        for pool in pools
        if _target_is_ahead(pool, current_price)
    ]
    candidates = sorted(candidates, key=lambda c: c.score, reverse=True)
    if not candidates:
        return DOLSelection(None, [], reason_code="UNCLEAR_DOL")
    selected = _select_with_tiebreakers(
        candidates,
        current_price,
        prefer_range_boundary=structure.detected and not prefer_actionable_targets,
        prefer_current_day=prefer_actionable_targets,
    )
    if len(candidates) > 1:
        runner_up = candidates[1] if candidates[0] == selected else candidates[0]
        if selected.direction != runner_up.direction and abs(selected.score - runner_up.score) <= 5:
            return DOLSelection(None, candidates, ambiguous=True, reason_code="DOL_AMBIGUOUS")
    return DOLSelection(selected, candidates)


def _score_pool(
    pool: LiquidityPool,
    active_range: DealingRange,
    current_price: float,
    atr: float,
    sweeps: Sequence[SweepEvent],
    displacement: DisplacementSignal,
    structure: StructureSignal,
    ssmt: SSMTSignal,
    time_context: object,
    htf_direction: str | None,
    direction_hierarchy: object | None,
    hrlr_lrlr: object | None,
    mmxm_grade: object | None,
    judas_swing: object | None,
    nine_am_model: object | None,
    include_execution_factors: bool,
    prefer_actionable_targets: bool,
) -> DOLCandidate:
    score = 0
    reasoning: list[str] = []
    if pool.liquidity_type == "ERL":
        score += 20
        reasoning.append(f"{pool.label} is external range liquidity")
    elif pool.liquidity_type == "IRL":
        score += 10
        reasoning.append(f"{pool.label} is internal range liquidity")
    else:
        score += 5
    if prefer_actionable_targets and pool.source == "current_day":
        score -= 10
        reasoning.append("Current-day extreme is session context, not fresh liquidity by itself")
    if active_range.current_position == "premium" and pool.direction == "sellside":
        score += 20
        reasoning.append("HTF price is trading in premium")
    elif active_range.current_position == "discount" and pool.direction == "buyside":
        score += 20
        reasoning.append("HTF price is trading in discount")
    elif active_range.current_position == "equilibrium":
        score += 5
        reasoning.append("Price is near equilibrium")
    if pool.price >= active_range.high or pool.price <= active_range.low or pool.label in {"active_range_high", "active_range_low"}:
        score += 15
        reasoning.append("Target sits at or beyond active range boundary")
    if htf_direction == pool.direction:
        score += 15
        reasoning.append("D1/H4/H1 narrative supports this draw")
    hierarchy_direction = getattr(direction_hierarchy, "dominant_direction", None)
    active_level = getattr(direction_hierarchy, "active_level", None)
    if hierarchy_direction == pool.direction:
        score += 10
        reasoning.append("Direction liquidity hierarchy supports this draw")
        direction_timeframes = set(getattr(active_level, "direction_timeframes", []) or [])
        irl_erl_timeframe = getattr(active_level, "irl_erl_timeframe", None)
        if pool.timeframe in direction_timeframes or pool.timeframe == irl_erl_timeframe:
            score += 5
            reasoning.append(f"{pool.timeframe} aligns with active direction liquidity layer")
    elif hierarchy_direction in {"buyside", "sellside"}:
        score -= 10
        reasoning.append("Direction liquidity hierarchy favors the opposite side")
    hrlr_target_direction = getattr(hrlr_lrlr, "target_direction", None)
    target_lrlr = getattr(hrlr_lrlr, "target_lrlr", None)
    if getattr(hrlr_lrlr, "hrlr_taken", False) and hrlr_target_direction == pool.direction:
        score += 15
        reasoning.append("HRLR was taken; LRLR target supports this draw")
        if target_lrlr is not None and abs(pool.price - target_lrlr.price) <= max(atr * 2.0, 0.1):
            score += 5
            reasoning.append("DOL is near the active LRLR stack")
    elif getattr(hrlr_lrlr, "hrlr_taken", False) and hrlr_target_direction in {"buyside", "sellside"}:
        score -= 10
        reasoning.append("HRLR/LRLR sequence favors the opposite side")
    mmxm_direction = getattr(mmxm_grade, "direction", None)
    if getattr(mmxm_grade, "status", None) == "complete" and mmxm_direction == pool.direction:
        score += 10
        reasoning.append(f"{getattr(mmxm_grade, 'model', 'MMXM')} swing grading supports this draw")
        terminus_price = getattr(mmxm_grade, "terminus_price", None)
        if terminus_price is not None and abs(pool.price - terminus_price) <= max(atr * 2.0, 0.1):
            score += 5
            reasoning.append("DOL is near the MMXM terminus")
    elif getattr(mmxm_grade, "status", None) == "complete" and mmxm_direction in {"buyside", "sellside"}:
        score -= 5
        reasoning.append("MMXM swing grading favors the opposite side")
    judas_target_direction = getattr(judas_swing, "target_direction", None)
    if getattr(judas_swing, "detected", False) and judas_target_direction == pool.direction:
        score += 15
        reasoning.append("Classic Judas Swing supports this draw")
        target_price = getattr(judas_swing, "target_price", None)
        if target_price is not None and abs(pool.price - target_price) <= max(atr * 2.0, 0.1):
            score += 5
            reasoning.append("DOL is near the Judas opening-range target")
    elif getattr(judas_swing, "detected", False) and judas_target_direction in {"buyside", "sellside"}:
        score -= 5
        reasoning.append("Classic Judas Swing favors the opposite side")
    nine_am_direction = getattr(nine_am_model, "direction", None)
    if getattr(nine_am_model, "status", None) == "confirmed" and nine_am_direction == pool.direction:
        score += 10
        reasoning.append("09AM model supports this draw")
        target_price = getattr(nine_am_model, "target_price", None)
        if target_price is not None and abs(pool.price - target_price) <= max(atr * 2.0, 0.1):
            score += 5
            reasoning.append("DOL is near the 09AM model target")
    elif getattr(nine_am_model, "status", None) == "confirmed" and nine_am_direction in {"buyside", "sellside"}:
        score -= 5
        reasoning.append("09AM model favors the opposite side")
    execution_applicable = include_execution_factors and htf_direction in (None, "neutral", pool.direction)
    if execution_applicable:
        opposite = "buyside" if pool.direction == "sellside" else "sellside"
        if any(sweep.direction == opposite for sweep in sweeps):
            score += 15
            reasoning.append(f"Recent opposite-side {opposite} sweep supports this draw")
    wanted_displacement = "bullish" if pool.direction == "buyside" else "bearish"
    if execution_applicable and displacement.detected and displacement.direction == wanted_displacement:
        score += 10
        reasoning.append(f"{wanted_displacement.title()} displacement confirms direction")
    if execution_applicable and structure.detected and structure.direction == wanted_displacement:
        score += 10
        reasoning.append(f"{wanted_displacement.title()} MSS confirms direction")
    wanted_ssmt = "bullish" if pool.direction == "buyside" else "bearish"
    if execution_applicable and ssmt.detected and ssmt.type == wanted_ssmt:
        score += 5
        reasoning.append(f"{wanted_ssmt.title()} SSMT confirms manipulation")
    if getattr(time_context, "killzone", False):
        score += 5
        reasoning.append("Analysis is inside London/New York killzone")
    distance_atr = abs(pool.price - current_price) / atr if atr > 0 else 0
    penalty = _distance_penalty(distance_atr, prefer_actionable_targets)
    score -= penalty
    if penalty:
        reasoning.append(f"Target proximity penalty: -{penalty}")
    final_score = max(0, min(100, int(round(score))))
    return DOLCandidate(
        label=pool.label,
        timeframe=pool.timeframe,
        liquidity_type=pool.liquidity_type,
        direction=pool.direction,
        price=pool.price,
        score=final_score,
        confidence=confidence_from_score(final_score),
        reasoning=reasoning,
    )


def _target_is_ahead(pool: LiquidityPool, current_price: float) -> bool:
    if pool.direction == "buyside":
        return pool.price > current_price
    return pool.price < current_price


def _select_with_tiebreakers(
    candidates: Sequence[DOLCandidate],
    current_price: float,
    prefer_range_boundary: bool = False,
    prefer_current_day: bool = False,
) -> DOLCandidate:
    top_score = candidates[0].score
    close = [candidate for candidate in candidates if top_score - candidate.score <= 10]
    close = sorted(
        close,
        key=lambda c: (
            c.score,
            0 if prefer_current_day and c.label in {"current_day_high", "current_day_low"} else 1,
            1 if prefer_range_boundary and c.label in {"active_range_high", "active_range_low"} else 0,
            1 if c.liquidity_type == "ERL" else 0,
            1 if c.timeframe == "H4" else 0,
            -abs(c.price - current_price),
        ),
        reverse=True,
    )
    return close[0]


def _distance_penalty(distance_atr: float, prefer_actionable_targets: bool) -> int:
    if not prefer_actionable_targets:
        if distance_atr > 8:
            return 15
        if distance_atr > 5:
            return 10
        if distance_atr > 3:
            return 5
        return 0
    if distance_atr > 30:
        return 60
    if distance_atr > 20:
        return 45
    if distance_atr > 12:
        return 30
    if distance_atr > 8:
        return 20
    if distance_atr > 5:
        return 15
    if distance_atr > 3:
        return 10
    if distance_atr > 1.5:
        return 5
    return 0

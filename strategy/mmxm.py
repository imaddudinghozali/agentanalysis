from __future__ import annotations

from dataclasses import dataclass

from .range import DealingRange


@dataclass(frozen=True)
class MMXMSwingGrade:
    status: str
    model: str | None = None
    direction: str | None = None
    phase: str | None = None
    quadrant: float | None = None
    fib_position: float | None = None
    terminus_price: float | None = None
    terminus_side: str | None = None
    range_timeframe: str | None = None
    reasoning: list[str] | None = None


def build_mmxm_swing_grade(
    active_range: DealingRange | None,
    draw_direction: str | None,
) -> MMXMSwingGrade:
    if active_range is None:
        return MMXMSwingGrade("insufficient", reasoning=["No active dealing range for MMXM swing grading"])
    if active_range.high <= active_range.low:
        return MMXMSwingGrade("insufficient", reasoning=["Invalid active dealing range for MMXM swing grading"])
    direction = draw_direction if draw_direction in {"buyside", "sellside"} else active_range.direction_hint
    if direction not in {"buyside", "sellside"}:
        return MMXMSwingGrade(
            "neutral",
            range_timeframe=active_range.timeframe,
            fib_position=_fib_position(active_range),
            quadrant=_nearest_quadrant(_fib_position(active_range)),
            reasoning=["MMXM model is neutral until DOL direction is clear"],
        )

    fib = _fib_position(active_range)
    quadrant = _nearest_quadrant(fib)
    model = "MMBM" if direction == "buyside" else "MMSM"
    terminus_side = "buyside" if direction == "buyside" else "sellside"
    terminus_price = active_range.high if direction == "buyside" else active_range.low
    phase = _phase(direction, fib)
    return MMXMSwingGrade(
        status="complete",
        model=model,
        direction=direction,
        phase=phase,
        quadrant=quadrant,
        fib_position=fib,
        terminus_price=terminus_price,
        terminus_side=terminus_side,
        range_timeframe=active_range.timeframe,
        reasoning=[
            f"{model} uses Fibonacci quadrant {quadrant:g} inside {active_range.timeframe} dealing range",
            f"Terminus is {terminus_side} liquidity at {terminus_price}",
        ],
    )


def _fib_position(active_range: DealingRange) -> float:
    value = (active_range.current_price - active_range.low) / (active_range.high - active_range.low)
    return max(0.0, min(1.0, value))


def _nearest_quadrant(value: float) -> float:
    return min((0.0, 0.25, 0.5, 0.75, 1.0), key=lambda quadrant: abs(value - quadrant))


def _phase(direction: str, fib: float) -> str:
    if direction == "sellside":
        if fib >= 0.75:
            return "premium_distribution"
        if fib >= 0.5:
            return "sell_model_repricing"
        if fib >= 0.25:
            return "delivery_below_equilibrium"
        return "sellside_terminus"
    if fib <= 0.25:
        return "discount_accumulation"
    if fib <= 0.5:
        return "buy_model_repricing"
    if fib <= 0.75:
        return "delivery_above_equilibrium"
    return "buyside_terminus"

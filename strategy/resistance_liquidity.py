from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .common import Candle, StrategyConfig, average_true_range
from .liquidity import SweepEvent
from .range import DealingRange
from .swing import SwingPoint


@dataclass(frozen=True)
class LRLRRun:
    direction: str
    price: float
    swing_count: int
    start_time: object
    end_time: object
    kind: str


@dataclass(frozen=True)
class HRLRContext:
    status: str
    hrlr_taken: bool = False
    hrlr_direction: str | None = None
    hrlr_price: float | None = None
    hrlr_time: object | None = None
    target_direction: str | None = None
    target_lrlr: LRLRRun | None = None
    lrlr_runs: list[LRLRRun] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)


def build_hrlr_lrlr_context(
    candles: Sequence[Candle],
    swings: Sequence[SwingPoint],
    sweeps: Sequence[SweepEvent],
    active_range: DealingRange | None,
    config: StrategyConfig,
) -> HRLRContext:
    if not candles or not swings:
        return HRLRContext("insufficient", reasoning=["M15 swings are insufficient for HRLR/LRLR"])

    current_price = candles[-1].close
    atr = average_true_range(candles) or _fallback_range(active_range)
    lrlr_runs = _detect_lrlr_runs(swings, current_price, atr)
    latest_hrlr = _latest_hrlr_sweep(sweeps)
    if latest_hrlr is None:
        return HRLRContext(
            "awaiting_hrlr",
            lrlr_runs=lrlr_runs,
            reasoning=["No rejected liquidity run has taken a strong swing point yet"],
        )

    target_direction = _opposite(latest_hrlr.direction)
    target_lrlr = _nearest_run(lrlr_runs, target_direction, current_price)
    status = "hrlr_to_lrlr" if target_lrlr is not None else "hrlr_taken_no_lrlr"
    reasoning = [
        f"{latest_hrlr.direction} HRLR was taken at {latest_hrlr.price}",
        f"Next liquidity draw looks {target_direction}",
    ]
    if target_lrlr is not None:
        reasoning.append(f"{target_direction} LRLR stacks {target_lrlr.swing_count} swings near {target_lrlr.price}")
    else:
        reasoning.append(f"No actionable {target_direction} LRLR stack is ahead of price")
    return HRLRContext(
        status=status,
        hrlr_taken=True,
        hrlr_direction=latest_hrlr.direction,
        hrlr_price=latest_hrlr.price,
        hrlr_time=latest_hrlr.candle_time,
        target_direction=target_direction,
        target_lrlr=target_lrlr,
        lrlr_runs=lrlr_runs,
        reasoning=reasoning,
    )


def _detect_lrlr_runs(swings: Sequence[SwingPoint], current_price: float, atr: float) -> list[LRLRRun]:
    tolerance = max(atr * 1.5, 0.1)
    runs: list[LRLRRun] = []
    for kind, direction in (("high", "buyside"), ("low", "sellside")):
        same_kind = [swing for swing in swings if swing.kind == kind][-12:]
        for index in range(len(same_kind) - 1):
            cluster = [same_kind[index]]
            for swing in same_kind[index + 1 :]:
                prices = [item.price for item in [*cluster, swing]]
                if max(prices) - min(prices) <= tolerance:
                    cluster.append(swing)
            if len(cluster) < 2:
                continue
            price = max(item.price for item in cluster) if direction == "buyside" else min(item.price for item in cluster)
            if direction == "buyside" and price <= current_price:
                continue
            if direction == "sellside" and price >= current_price:
                continue
            runs.append(
                LRLRRun(
                    direction=direction,
                    price=price,
                    swing_count=len(cluster),
                    start_time=cluster[0].time,
                    end_time=cluster[-1].time,
                    kind=kind,
                )
            )
    return _nearest_runs(_dedupe_runs(runs), current_price)


def _latest_hrlr_sweep(sweeps: Sequence[SweepEvent]) -> SweepEvent | None:
    for sweep in reversed(sweeps):
        return sweep
    return None


def _nearest_run(runs: Sequence[LRLRRun], direction: str, current_price: float) -> LRLRRun | None:
    directional = [run for run in runs if run.direction == direction]
    if not directional:
        return None
    return min(directional, key=lambda run: abs(run.price - current_price))


def _dedupe_runs(runs: Sequence[LRLRRun]) -> list[LRLRRun]:
    unique: list[LRLRRun] = []
    seen: set[tuple[str, float, object]] = set()
    for run in sorted(runs, key=lambda item: (item.direction, item.end_time)):
        key = (run.direction, round(run.price, 5), run.end_time)
        if key in seen:
            continue
        seen.add(key)
        unique.append(run)
    return unique


def _nearest_runs(runs: Sequence[LRLRRun], current_price: float) -> list[LRLRRun]:
    limited: list[LRLRRun] = []
    for direction in ("buyside", "sellside"):
        directional = [run for run in runs if run.direction == direction]
        directional = sorted(directional, key=lambda run: (abs(run.price - current_price), -run.swing_count))
        limited.extend(directional[:5])
    return sorted(limited, key=lambda run: (run.direction, abs(run.price - current_price)))


def _fallback_range(active_range: DealingRange | None) -> float:
    if active_range is None:
        return 1.0
    return max(abs(active_range.high - active_range.low) / 20.0, 0.1)


def _opposite(direction: str) -> str:
    return "sellside" if direction == "buyside" else "buyside"

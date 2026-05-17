from __future__ import annotations

from dataclasses import dataclass, field

from .displacement import DisplacementSignal
from .dol import DOLCandidate
from .fvg import FVGSignal
from .liquidity import SweepEvent
from .range import DealingRange
from .ssmt import SSMTSignal
from .structure import StructureSignal


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failed_reasons: list[str] = field(default_factory=list)
    required_confirmations: list[str] = field(default_factory=list)
    present_confirmations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TradeIdea:
    action: str
    reason_code: str
    blocking_conditions: list[str] = field(default_factory=list)
    reason_wait: str | None = None
    entry_model: str | None = None
    entry_area: dict[str, float] | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    invalidation: str | float | None = None


@dataclass(frozen=True)
class TradeGateDecision:
    active_model: str | None
    bias: str
    trade_idea: TradeIdea
    gate_result: GateResult


def generate_trade_idea(
    selected_dol: DOLCandidate | None,
    active_range: DealingRange | None,
    sweep: SweepEvent | None,
    ssmt: SSMTSignal,
    displacement: DisplacementSignal,
    structure: StructureSignal,
    fvg: FVGSignal,
    warnings: list[str],
    dol_reason_code: str | None = None,
) -> TradeGateDecision:
    if active_range is None:
        return _wait(None, "WAIT", "NO_ACTIVE_DEALING_RANGE", ["htf_context"], ["sweep", "displacement", "mss", "fvg"], [])
    critical = [
        warning
        for warning in warnings
        if warning
        in {
            "MISSING_HTF_CONTEXT",
            "INSUFFICIENT_HTF_DATA",
            "INSUFFICIENT_DATA",
            "STALE_DATA",
            "HTF_CONFLICT",
            "DOL_AMBIGUOUS",
            "SSMT_UNAVAILABLE",
            "SECONDARY_STALE",
            "SSMT_TIMESTAMP_MISMATCH",
        }
    ]
    if critical:
        bias = "BUY" if selected_dol and selected_dol.direction == "buyside" else "SELL" if selected_dol else "WAIT"
        reason_code = "SSMT_UNAVAILABLE" if _has_ssmt_blocker(critical) else critical[0]
        return _wait(None, bias, reason_code, ["data"], ["sweep", "displacement", "mss", "fvg"], [], selected_dol)
    if selected_dol is None:
        return _wait("NO_DOL", "WAIT", dol_reason_code or "UNCLEAR_DOL", ["dol"], ["sweep", "displacement", "mss", "fvg"], [])
    bias = "BUY" if selected_dol.direction == "buyside" else "SELL"
    if selected_dol.score < 60:
        return _wait(None, bias, "UNCLEAR_DOL", ["dol"], ["sweep", "displacement", "mss", "fvg"], [])
    if "H4_MISSING" in warnings and selected_dol.confidence != "high":
        return _wait(None, bias, "UNCLEAR_DOL", ["htf_context"], ["sweep", "displacement", "mss", "fvg"], [])
    if active_range.current_position == "equilibrium" and selected_dol.score < 80:
        return _wait(None, bias, "UNCLEAR_DOL", ["dol"], ["sweep", "displacement", "mss", "fvg"], [])
    if not sweep:
        return _wait(None, bias, "MISSING_SWEEP", ["sweep"], ["sweep", "displacement", "mss", "fvg"], [])
    expected_sweep = "sellside" if selected_dol.direction == "buyside" else "buyside"
    expected_signal = "bullish" if selected_dol.direction == "buyside" else "bearish"
    if sweep.direction != expected_sweep:
        return _wait("CONTEXT_CONFLICT", bias, "HTF_M15_CONFLICT", ["context"], ["sweep", "displacement", "mss", "fvg"], ["sweep"])
    active_model = "IRL_TO_ERL_BULLISH" if bias == "BUY" else "IRL_TO_ERL_BEARISH"
    required = ["sweep", "displacement", "mss", "fvg"]
    present = ["sweep"]
    missing: list[tuple[str, str]] = []
    if displacement.detected and displacement.direction == expected_signal:
        present.append("displacement")
    else:
        missing.append(("displacement", "MISSING_DISPLACEMENT"))
    if structure.detected and structure.direction == expected_signal:
        present.append("mss")
    else:
        missing.append(("mss", "MISSING_MSS"))
    if fvg.detected and fvg.direction == expected_signal:
        present.append("fvg")
    else:
        missing.append(("fvg", "MISSING_FVG"))
    invalidation = _invalidation_from_sweep(sweep, expected_signal)
    if invalidation is None:
        return _wait(active_model, bias, "MISSING_INVALIDATION", ["invalidation"], required, present)
    if missing:
        condition, reason_code = missing[0]
        return _wait(active_model, bias, reason_code, [condition], required, present, selected_dol)
    action = bias
    return TradeGateDecision(
        active_model=active_model,
        bias=bias,
        trade_idea=TradeIdea(
            action=action,
            reason_code="GATE_COMPLETE",
            blocking_conditions=[],
            entry_model=active_model,
            entry_area={"lower": fvg.lower, "upper": fvg.upper} if fvg.lower is not None and fvg.upper is not None else None,
            stop_loss=float(invalidation),
            take_profit=selected_dol.price,
            invalidation=float(invalidation),
        ),
        gate_result=GateResult(True, [], required, present),
    )


def _wait(
    active_model: str | None,
    bias: str,
    reason_code: str,
    blocking: list[str],
    required: list[str],
    present: list[str],
    selected_dol: DOLCandidate | None = None,
) -> TradeGateDecision:
    return TradeGateDecision(
        active_model=active_model,
        bias=bias,
        trade_idea=TradeIdea(
            action="WAIT",
            reason_code=reason_code,
            blocking_conditions=blocking,
            reason_wait=_wait_reason(reason_code),
            take_profit=selected_dol.price if selected_dol is not None else None,
            invalidation=_wait_reason(reason_code),
        ),
        gate_result=GateResult(False, [reason_code], required, present),
    )


def _wait_reason(reason_code: str) -> str:
    reasons = {
        "NO_ACTIVE_DEALING_RANGE": "No valid higher-timeframe dealing range contains current price.",
        "MISSING_HTF_CONTEXT": "Required higher-timeframe context is incomplete.",
        "INSUFFICIENT_HTF_DATA": "Required higher-timeframe candle history is insufficient.",
        "INSUFFICIENT_DATA": "Required market data is insufficient for analysis.",
        "HTF_CONFLICT": "D1/H4/H1 context is conflicting, so M15 execution is not allowed.",
        "SSMT_UNAVAILABLE": "SSMT confirmation is unavailable, so the setup remains WAIT.",
        "SECONDARY_STALE": "Secondary symbol data is stale, so SSMT cannot be trusted.",
        "SSMT_TIMESTAMP_MISMATCH": "Primary and secondary candles are not timestamp-aligned.",
        "UNCLEAR_DOL": "Draw on liquidity is not strong enough for execution.",
        "DOL_AMBIGUOUS": "Opposite-side DOL candidates are too close in score.",
        "MISSING_SWEEP": "M15 has not swept the opposite-side liquidity required by the model.",
        "HTF_M15_CONFLICT": "M15 sweep direction conflicts with the selected HTF DOL.",
        "MISSING_DISPLACEMENT": "Displacement has not confirmed in the DOL direction.",
        "MISSING_MSS": "MSS confirmation is missing, so action remains WAIT.",
        "MISSING_FVG": "No valid FVG entry area is present in the DOL direction.",
        "MISSING_INVALIDATION": "No deterministic invalidation level is available.",
    }
    return reasons.get(reason_code, f"Action remains WAIT because {reason_code} is present.")


def _has_ssmt_blocker(warnings: list[str]) -> bool:
    return any(warning in {"SSMT_UNAVAILABLE", "SECONDARY_STALE", "SSMT_TIMESTAMP_MISMATCH"} for warning in warnings)


def _invalidation_from_sweep(sweep: SweepEvent, expected_signal: str) -> float | None:
    if expected_signal == "bullish":
        return sweep.price
    if expected_signal == "bearish":
        return sweep.price
    return None

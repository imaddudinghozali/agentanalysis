from __future__ import annotations

from typing import Any, Mapping, Sequence

from .common import DataCoverage, RULE_VERSION, StrategyConfig, asdict_clean, normalize_candles, parse_time, timeframe_swing_params
from .displacement import detect_displacement
from .dol import score_dol_candidates
from .fvg import detect_fvg
from .htf import build_htf_narrative
from .liquidity import build_liquidity_pools, detect_sweeps, latest_sweep
from .narrative import build_narrative
from .range import build_active_dealing_range
from .ssmt import detect_ssmt
from .structure import detect_mss
from .swing import detect_swings
from .time_context import get_time_context
from .trade_idea import generate_trade_idea


def analyze_market(
    market_data: Mapping[str, Mapping[str, Sequence[Mapping[str, Any]]]],
    primary_symbol: str = "XAUUSD",
    secondary_symbol: str = "XAGUSD",
    execution_timeframe: str = "M15",
    context_timeframes: Sequence[str] = ("H4", "H1", "D1"),
    analysis_as_of: Any | None = None,
    mode: str = "normal",
    config: StrategyConfig | None = None,
) -> dict[str, Any]:
    cfg = config or StrategyConfig()
    as_of = parse_time(analysis_as_of)
    primary = market_data.get(primary_symbol, {})
    secondary = market_data.get(secondary_symbol, {})
    m15 = normalize_candles(primary.get(execution_timeframe, []), as_of)
    h1 = normalize_candles(primary.get("H1", []), as_of)
    h4 = normalize_candles(primary.get("H4", []), as_of)
    d1 = normalize_candles(primary.get("D1", []), as_of)
    secondary_m15 = normalize_candles(secondary.get(execution_timeframe, []), as_of)
    coverage = _data_coverage(m15, h1, h4, d1, cfg)
    context_map = {"H1": h1, "H4": h4}
    execution_price = m15[-1].close if m15 else None
    active_range, htf_swings = build_active_dealing_range(
        context_map, cfg, prefer=("H4", "H1"), current_price=execution_price
    )
    htf_narrative = build_htf_narrative(h1, h4, d1, active_range, htf_swings, cfg)
    left, right, major = timeframe_swing_params("M15", cfg)
    m15_swings = detect_swings(m15, left, right, "M15", major)
    sweeps = detect_sweeps(m15, m15_swings, cfg, "M15")
    sweep = latest_sweep(sweeps)
    displacement = detect_displacement(m15, cfg)
    structure = detect_mss(m15, m15_swings, sweep, cfg)
    expected_fvg_direction = structure.direction or displacement.direction
    fvg = detect_fvg(m15, cfg, expected_fvg_direction)
    ssmt = detect_ssmt(m15, secondary_m15, as_of, cfg)
    time_context = get_time_context(as_of)
    pools = build_liquidity_pools(active_range, htf_swings, d1)
    dol_selection = score_dol_candidates(
        pools,
        active_range,
        m15,
        sweeps,
        displacement,
        structure,
        ssmt,
        time_context,
        cfg,
        htf_direction=htf_narrative.direction,
    )
    warnings = list(coverage.warnings)
    if htf_narrative.reason_code in {"HTF_CONFLICT", "MISSING_HTF_CONTEXT"} and htf_narrative.reason_code not in warnings:
        warnings.append(htf_narrative.reason_code)
    if ssmt.warning and ssmt.warning not in warnings:
        warnings.append(ssmt.warning)
    if dol_selection.reason_code == "DOL_AMBIGUOUS":
        warnings.append("DOL_AMBIGUOUS")
    trade = generate_trade_idea(
        dol_selection.selected,
        active_range,
        sweep,
        ssmt,
        displacement,
        structure,
        fvg,
        warnings,
        dol_selection.reason_code,
    )
    reasoning = _reasoning(active_range, htf_narrative, dol_selection.selected, sweep, ssmt, displacement, structure, fvg, trade.trade_idea.reason_code)
    narrative = build_narrative(dol_selection.selected, trade, reasoning, warnings)
    return asdict_clean(
        {
            "primary_symbol": primary_symbol,
            "secondary_symbol": secondary_symbol,
            "execution_timeframe": execution_timeframe,
            "context_timeframes": list(context_timeframes),
            "analysis_as_of": as_of,
            "rule_version": RULE_VERSION,
            "market_state": _market_state(sweep, displacement, structure),
            "active_model": trade.active_model,
            "bias": trade.bias,
            "action": trade.trade_idea.action,
            "data_coverage": coverage,
            "time_context": time_context,
            "htf_context": _htf_context(active_range, htf_narrative, dol_selection.selected),
            "liquidity": {
                "recently_taken": sweeps,
                "next_dol": dol_selection.selected,
            },
            "dol_candidates": dol_selection.candidates,
            "ssmt": ssmt,
            "confirmation": {
                "sweep": sweep is not None,
                "displacement": displacement.detected,
                "mss": structure.detected,
                "fvg": fvg.detected,
            },
            "trade_idea": trade.trade_idea,
            "gate_result": trade.gate_result,
            "confidence": dol_selection.selected.confidence if dol_selection.selected else "unavailable",
            "reasoning": reasoning,
            "warnings": warnings,
            "narrative": narrative,
            "mode": mode,
        }
    )


def _data_coverage(m15: list[Any], h1: list[Any], h4: list[Any], d1: list[Any], cfg: StrategyConfig) -> DataCoverage:
    missing: list[str] = []
    warnings: list[str] = []
    degraded = False
    if len(m15) < cfg.minimum_m15_candles:
        missing.append("XAUUSD_M15")
        warnings.append("INSUFFICIENT_DATA")
    if len(h1) < cfg.minimum_htf_candles_h1:
        missing.append("XAUUSD_H1")
        warnings.append("MISSING_HTF_CONTEXT")
        warnings.append("INSUFFICIENT_HTF_DATA")
    if len(h4) < cfg.minimum_htf_candles_h4:
        missing.append("XAUUSD_H4")
        degraded = len(h1) >= cfg.minimum_htf_candles_h1
        warnings.append("H4_MISSING" if degraded else "MISSING_HTF_CONTEXT")
        if not degraded:
            warnings.append("INSUFFICIENT_HTF_DATA")
    if d1 and len(d1) < cfg.minimum_htf_candles_d1:
        warnings.append("D1_INSUFFICIENT")
    if not d1:
        warnings.append("D1_MISSING")
    status = "complete" if not missing else "degraded" if degraded else "insufficient"
    return DataCoverage(status=status, missing=missing, degraded_mode=degraded, warnings=_dedupe(warnings))


def _htf_context(active_range: Any, htf_narrative: Any, selected_dol: Any) -> dict[str, Any]:
    if active_range is None:
        return {
            "dealing_range_high": None,
            "dealing_range_low": None,
            "equilibrium": None,
            "current_position": "unknown",
            "dol_direction": selected_dol.direction if selected_dol else None,
            "narrative_direction": htf_narrative.direction,
            "narrative_status": htf_narrative.status,
            "conflict": htf_narrative.conflict,
            "frames": htf_narrative.frames,
        }
    return {
        "dealing_range_high": active_range.high,
        "dealing_range_low": active_range.low,
        "equilibrium": active_range.equilibrium,
        "current_position": active_range.current_position,
        "dol_direction": selected_dol.direction if selected_dol else active_range.direction_hint,
        "narrative_direction": htf_narrative.direction,
        "narrative_status": htf_narrative.status,
        "conflict": htf_narrative.conflict,
        "frames": htf_narrative.frames,
        "timeframe": active_range.timeframe,
    }


def _market_state(sweep: Any, displacement: Any, structure: Any) -> str:
    if sweep and displacement.detected and structure.detected:
        return "post_sweep_displacement_mss"
    if sweep and displacement.detected:
        return "post_sweep_displacement"
    if sweep:
        return "post_sweep"
    return "building_context"


def _reasoning(active_range: Any, htf_narrative: Any, selected_dol: Any, sweep: Any, ssmt: Any, displacement: Any, structure: Any, fvg: Any, reason_code: str) -> list[str]:
    lines: list[str] = []
    if active_range is not None:
        lines.append(f"HTF price is trading in {active_range.current_position}")
    lines.extend(htf_narrative.reasoning)
    if selected_dol is not None:
        lines.append(f"HTF DOL points toward {selected_dol.label} ({selected_dol.direction})")
    if sweep is not None:
        lines.append(f"M15 swept {sweep.direction} liquidity")
    if ssmt.detected:
        lines.append(f"{ssmt.type.title()} SSMT detected between XAUUSD and XAGUSD")
    elif not ssmt.available:
        lines.append(f"SSMT unavailable: {ssmt.sync_status}")
    if displacement.detected:
        lines.append(f"{displacement.direction.title()} displacement detected")
    if structure.detected:
        lines.append(f"{structure.direction.title()} MSS detected")
    if fvg.detected:
        lines.append(f"{fvg.direction.title()} FVG detected")
    if reason_code != "GATE_COMPLETE":
        lines.append(f"Action remains WAIT due to {reason_code}")
    return lines


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out

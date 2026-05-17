from __future__ import annotations


def build_narrative(result: dict) -> str:
    trade_idea = result.get("trade_idea", {})
    next_dol = result.get("liquidity", {}).get("next_dol") or {}
    dol_label = next_dol.get("label", "no selected DOL")
    reason_code = trade_idea.get("reason_code", "UNKNOWN")
    action = trade_idea.get("action", result.get("action", "WAIT"))
    position = result.get("htf_context", {}).get("current_position", "unknown")
    confirmations = result.get("confirmation", {})
    present = [name for name, enabled in confirmations.items() if enabled]
    missing = trade_idea.get("blocking_conditions", [])

    parts = [
        f"Action is {action}.",
        f"Selected DOL is {dol_label}.",
        f"HTF location is {position}.",
        f"Reason code is {reason_code}.",
    ]
    if present:
        parts.append(f"Present M15 confirmations: {', '.join(present)}.")
    if missing:
        parts.append(f"Missing confirmation keeps the engine waiting: {', '.join(missing)}.")
    return " ".join(parts)


def build_report_payload(result: dict) -> dict:
    narrative = result.get("narrative_report") or result.get("narrative") or build_narrative(result)
    trade_idea = result.get("trade_idea", {})
    liquidity = result.get("liquidity", {})
    next_dol = liquidity.get("next_dol")
    gate_result = result.get("gate_result", {})
    return {
        "primary_symbol": result.get("primary_symbol"),
        "secondary_symbol": result.get("secondary_symbol"),
        "execution_timeframe": result.get("execution_timeframe"),
        "context_timeframes": result.get("context_timeframes", []),
        "analysis_as_of": result.get("analysis_as_of"),
        "rule_version": result.get("rule_version"),
        "action": trade_idea.get("action", result.get("action", "WAIT")),
        "reason_code": trade_idea.get("reason_code"),
        "active_model": result.get("active_model"),
        "bias": result.get("bias"),
        "data_coverage": result.get("data_coverage", {}),
        "htf_context": result.get("htf_context", {}),
        "selected_dol": next_dol,
        "dol_candidates": result.get("dol_candidates", []),
        "liquidity": liquidity,
        "ssmt": result.get("ssmt", {}),
        "confirmation": result.get("confirmation", {}),
        "trade_idea": trade_idea,
        "gate_result": gate_result,
        "blocking_conditions": trade_idea.get("blocking_conditions", []),
        "present_confirmations": gate_result.get("present_confirmations", []),
        "failed_reasons": gate_result.get("failed_reasons", []),
        "warnings": result.get("warnings", []),
        "narrative_report": narrative,
        "reasoning": result.get("reasoning", []),
    }

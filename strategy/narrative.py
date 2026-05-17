from __future__ import annotations

from .dol import DOLCandidate
from .trade_idea import TradeGateDecision


def build_narrative(
    selected_dol: DOLCandidate | None,
    trade: TradeGateDecision,
    reasoning: list[str],
    warnings: list[str],
) -> str:
    parts: list[str] = []
    if selected_dol is not None:
        parts.append(
            f"Selected DOL is {selected_dol.label} at {selected_dol.price} "
            f"with {selected_dol.confidence} confidence ({selected_dol.score})."
        )
    else:
        parts.append("Selected DOL is unavailable.")
    if trade.trade_idea.action == "WAIT":
        parts.append(f"Action is WAIT because {trade.trade_idea.reason_code}.")
    else:
        parts.append(f"Action is {trade.trade_idea.action}; reason code is {trade.trade_idea.reason_code}.")
    if reasoning:
        parts.append("Key evidence: " + "; ".join(reasoning[:5]) + ".")
    if warnings:
        parts.append("Warnings: " + ", ".join(warnings) + ".")
    return " ".join(parts)

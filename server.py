from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from schemas.market import AnalysisRequest
from services.analysis_service import AnalysisService
from storage.candles import CandleRepository


def _prepare_local_pywin32_paths() -> None:
    deps = Path(__file__).resolve().parent / ".deps"
    for path in (deps / "win32", deps / "win32" / "lib", deps / "pywin32_system32"):
        if path.exists():
            path_text = str(path)
            if path_text not in sys.path:
                sys.path.append(path_text)
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(path_text)


def _service() -> AnalysisService:
    db_path = os.getenv("TRADING_STRATEGY_DB_PATH")
    return AnalysisService(CandleRepository(Path(db_path) if db_path else None))


def _request_from_tool_args(
    *,
    primary_symbol: str,
    secondary_symbol: str | None,
    execution_timeframe: str,
    context_timeframes: list[str] | None,
    analysis_as_of: str | None,
    mode: str,
) -> AnalysisRequest:
    if not analysis_as_of:
        raise ValueError("analysis_as_of is required for reproducible analysis")
    return AnalysisRequest(
        primary_symbol=primary_symbol,
        secondary_symbol=secondary_symbol,
        execution_timeframe=execution_timeframe,
        context_timeframes=context_timeframes or ["H4", "H1", "D1"],
        analysis_as_of=analysis_as_of,
        mode=mode,
    )


try:
    _prepare_local_pywin32_paths()
    from mcp.server.fastmcp import FastMCP

    MCP_IMPORT_ERROR: str | None = None
except ImportError as exc:
    FastMCP = None  # type: ignore[assignment]
    MCP_IMPORT_ERROR = (
        "MCP SDK is not installed or its FastMCP import path changed. "
        "Install requirements.txt or run the FastAPI app directly with `uvicorn app:app --reload`."
    )


if FastMCP is not None:
    mcp = FastMCP("trading-strategy-discipline-engine")

    @mcp.tool()
    def analyze_market(
        primary_symbol: str = "XAUUSD",
        secondary_symbol: str = "XAGUSD",
        execution_timeframe: str = "M15",
        context_timeframes: list[str] | None = None,
        analysis_as_of: str | None = None,
        mode: str = "normal",
    ) -> dict[str, Any]:
        """Return the full deterministic market analysis."""
        request = _request_from_tool_args(
            primary_symbol=primary_symbol,
            secondary_symbol=secondary_symbol,
            execution_timeframe=execution_timeframe,
            context_timeframes=context_timeframes or ["H4", "H1", "D1"],
            analysis_as_of=analysis_as_of,
            mode=mode,
        )
        return _service().analyze(request)

    @mcp.tool()
    def detect_liquidity(
        primary_symbol: str = "XAUUSD",
        secondary_symbol: str = "XAGUSD",
        execution_timeframe: str = "M15",
        context_timeframes: list[str] | None = None,
        analysis_as_of: str | None = None,
        mode: str = "normal",
    ) -> dict[str, Any]:
        """Return liquidity pools, recently taken liquidity, and DOL candidates."""
        request = _request_from_tool_args(
            primary_symbol=primary_symbol,
            secondary_symbol=secondary_symbol,
            execution_timeframe=execution_timeframe,
            context_timeframes=context_timeframes,
            analysis_as_of=analysis_as_of,
            mode=mode,
        )
        return _service().detect_liquidity(request)

    @mcp.tool()
    def detect_ssmt(
        primary_symbol: str = "XAUUSD",
        secondary_symbol: str = "XAGUSD",
        execution_timeframe: str = "M15",
        context_timeframes: list[str] | None = None,
        analysis_as_of: str | None = None,
        mode: str = "normal",
    ) -> dict[str, Any]:
        """Return SSMT status, divergence type, quality, and sync state."""
        request = _request_from_tool_args(
            primary_symbol=primary_symbol,
            secondary_symbol=secondary_symbol,
            execution_timeframe=execution_timeframe,
            context_timeframes=context_timeframes,
            analysis_as_of=analysis_as_of,
            mode=mode,
        )
        return _service().detect_ssmt(request)

    @mcp.tool()
    def generate_trade_idea(
        primary_symbol: str = "XAUUSD",
        secondary_symbol: str = "XAGUSD",
        execution_timeframe: str = "M15",
        context_timeframes: list[str] | None = None,
        analysis_as_of: str | None = None,
        mode: str = "normal",
    ) -> dict[str, Any]:
        """Return WAIT/BUY/SELL trade idea with gate result and narrative."""
        request = _request_from_tool_args(
            primary_symbol=primary_symbol,
            secondary_symbol=secondary_symbol,
            execution_timeframe=execution_timeframe,
            context_timeframes=context_timeframes,
            analysis_as_of=analysis_as_of,
            mode=mode,
        )
        return _service().generate_trade_idea(request)
else:
    mcp = None


def main() -> None:
    if MCP_IMPORT_ERROR:
        raise SystemExit(MCP_IMPORT_ERROR)
    mcp.run()  # type: ignore[union-attr]


if __name__ == "__main__":
    main()

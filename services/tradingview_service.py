from __future__ import annotations

import asyncio
import json
import random
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from schemas.candle import CandlePayload
from schemas.market import AnalysisRequest
from services.analysis_service import AnalysisService
from storage.candles import CandleRepository, iso_utc


class TradingViewFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class TradingViewSeriesSpec:
    symbol: str
    timeframe: str
    tv_symbol: str
    resolution: str
    count: int


DEFAULT_SERIES = (
    TradingViewSeriesSpec("XAUUSD", "M15", "OANDA:XAUUSD", "15", 260),
    TradingViewSeriesSpec("XAUUSD", "H1", "OANDA:XAUUSD", "60", 150),
    TradingViewSeriesSpec("XAUUSD", "H4", "OANDA:XAUUSD", "240", 100),
    TradingViewSeriesSpec("XAUUSD", "D1", "OANDA:XAUUSD", "1D", 45),
    TradingViewSeriesSpec("XAGUSD", "M15", "OANDA:XAGUSD", "15", 260),
)

TIMEFRAME_DURATIONS = {
    "M15": timedelta(minutes=15),
    "H1": timedelta(hours=1),
    "H4": timedelta(hours=4),
    "D1": timedelta(days=1),
}


class TradingViewMarketDataService:
    def __init__(
        self,
        repository: CandleRepository,
        series: tuple[TradingViewSeriesSpec, ...] = DEFAULT_SERIES,
    ) -> None:
        self.repository = repository
        self.series = series

    async def refresh_and_analyze(self, analysis_service: AnalysisService) -> dict[str, Any]:
        fetched = await self.refresh_market_data()
        primary_m15 = fetched.get(("XAUUSD", "M15"), [])
        secondary_m15 = fetched.get(("XAGUSD", "M15"), [])
        if not primary_m15 or not secondary_m15:
            raise TradingViewFetchError("TradingView did not return enough M15 data for XAUUSD/XAGUSD")

        analysis_as_of = min(primary_m15[-1].time, secondary_m15[-1].time)
        result = analysis_service.analyze(
            AnalysisRequest(
                primary_symbol="XAUUSD",
                secondary_symbol="XAGUSD",
                execution_timeframe="M15",
                context_timeframes=["H4", "H1", "D1"],
                analysis_as_of=analysis_as_of,
                mode="normal",
            )
        )
        result["market_data_source"] = {
            "provider": "TradingView",
            "exchange": "OANDA",
            "analysis_as_of": iso_utc(analysis_as_of),
            "series": [
                {
                    "symbol": spec.symbol,
                    "timeframe": spec.timeframe,
                    "tv_symbol": spec.tv_symbol,
                    "rows_imported": len(fetched.get((spec.symbol, spec.timeframe), [])),
                    "last_candle_time": iso_utc(fetched[(spec.symbol, spec.timeframe)][-1].time)
                    if fetched.get((spec.symbol, spec.timeframe))
                    else None,
                }
                for spec in self.series
            ],
        }
        return result

    async def refresh_market_data(self) -> dict[tuple[str, str], list[CandlePayload]]:
        fetched: dict[tuple[str, str], list[CandlePayload]] = {}
        for spec in self.series:
            rows = await self._fetch_series(spec.tv_symbol, spec.resolution, spec.count)
            candles = self._rows_to_candles(spec.symbol, spec.timeframe, rows)
            if not candles:
                raise TradingViewFetchError(f"No closed candles returned for {spec.symbol} {spec.timeframe}")
            self.repository.bulk_upsert(candles, source="tradingview")
            fetched[(spec.symbol, spec.timeframe)] = candles
        return fetched

    async def _fetch_series(self, tv_symbol: str, resolution: str, count: int) -> list[dict[str, Any]]:
        try:
            import websockets
        except ImportError as exc:
            raise TradingViewFetchError("websockets is required to fetch TradingView data") from exc

        chart_session = self._session_name("cs")
        symbol_name = "symbol_1"
        series_name = "s1"
        rows: list[dict[str, Any]] = []
        try:
            async with websockets.connect(
                "wss://data.tradingview.com/socket.io/websocket",
                origin="https://www.tradingview.com",
                open_timeout=15,
                ping_interval=None,
                max_size=16_000_000,
            ) as websocket:
                await self._send(websocket, "set_auth_token", ["unauthorized_user_token"])
                await self._send(websocket, "chart_create_session", [chart_session, ""])
                await self._send(websocket, "switch_timezone", [chart_session, "Etc/UTC"])
                symbol_payload = "=" + json.dumps(
                    {"symbol": tv_symbol, "adjustment": "splits"},
                    separators=(",", ":"),
                )
                await self._send(websocket, "resolve_symbol", [chart_session, symbol_name, symbol_payload])
                await self._send(
                    websocket,
                    "create_series",
                    [chart_session, series_name, series_name, symbol_name, resolution, count],
                )
                deadline = asyncio.get_running_loop().time() + 30
                while asyncio.get_running_loop().time() < deadline:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=10)
                    for kind, payload in self._parse_frames(raw):
                        if kind == "heartbeat":
                            await websocket.send(payload)
                            continue
                        if kind != "json":
                            continue
                        if payload.get("m") in {"symbol_error", "series_error"}:
                            raise TradingViewFetchError(json.dumps(payload))
                        if payload.get("m") == "timescale_update":
                            series = payload.get("p", [None, {}])[1].get(series_name, {})
                            if series.get("s"):
                                rows = series["s"]
                        if payload.get("m") == "series_completed" and rows:
                            await self._send(websocket, "chart_delete_session", [chart_session])
                            return rows
        except (asyncio.TimeoutError, OSError) as exc:
            raise TradingViewFetchError(f"TradingView request failed for {tv_symbol} {resolution}: {exc}") from exc
        if rows:
            return rows
        raise TradingViewFetchError(f"No TradingView series returned for {tv_symbol} {resolution}")

    def _rows_to_candles(self, symbol: str, timeframe: str, rows: list[dict[str, Any]]) -> list[CandlePayload]:
        now = datetime.now(timezone.utc)
        duration = TIMEFRAME_DURATIONS[timeframe]
        candles: list[CandlePayload] = []
        for item in rows:
            values = item.get("v", [])
            if len(values) < 5:
                continue
            opened_at = datetime.fromtimestamp(float(values[0]), tz=timezone.utc).replace(microsecond=0)
            if opened_at + duration > now:
                continue
            candles.append(
                CandlePayload(
                    symbol=symbol,
                    timeframe=timeframe,
                    time=opened_at,
                    open=float(values[1]),
                    high=float(values[2]),
                    low=float(values[3]),
                    close=float(values[4]),
                    volume=float(values[5]) if len(values) > 5 and values[5] is not None else None,
                )
            )
        return candles

    def _session_name(self, prefix: str) -> str:
        suffix = "".join(random.choice(string.ascii_lowercase) for _ in range(12))
        return f"{prefix}_{suffix}"

    async def _send(self, websocket: Any, method: str, params: list[Any]) -> None:
        await websocket.send(self._frame({"m": method, "p": params}))

    def _frame(self, payload: dict[str, Any] | str) -> str:
        data = json.dumps(payload, separators=(",", ":")) if not isinstance(payload, str) else payload
        return f"~m~{len(data)}~m~{data}"

    def _parse_frames(self, raw: str) -> list[tuple[str, Any]]:
        frames: list[tuple[str, Any]] = []
        index = 0
        while index < len(raw):
            if not raw.startswith("~m~", index):
                break
            length_end = raw.find("~m~", index + 3)
            if length_end == -1:
                break
            size = int(raw[index + 3 : length_end])
            start = length_end + 3
            chunk = raw[start : start + size]
            if chunk.startswith("~h~"):
                frames.append(("heartbeat", raw[index : start + size]))
            else:
                try:
                    frames.append(("json", json.loads(chunk)))
                except json.JSONDecodeError:
                    frames.append(("raw", chunk))
            index = start + size
        return frames

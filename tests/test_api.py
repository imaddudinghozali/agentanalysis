from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import create_app
from services.tradingview_service import TradingViewFetchError


def _csv_rows(start: datetime, count: int, base: float = 2400.0, step_minutes: int = 15) -> str:
    rows = ["time,open,high,low,close,volume"]
    for index in range(count):
        time = start + timedelta(minutes=step_minutes * index)
        open_price = base + index * 0.1
        close = open_price + 0.05
        rows.append(
            f"{time.isoformat().replace('+00:00', 'Z')},{open_price:.2f},{open_price + 1:.2f},{open_price - 1:.2f},{close:.2f},100"
        )
    return "\n".join(rows)


def test_webhook_upserts_duplicate_candle(tmp_path):
    client = TestClient(create_app(tmp_path / "test.sqlite3"))
    payload = {
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "time": "2026-05-16T08:30:00-04:00",
        "open": 2400.1,
        "high": 2405.2,
        "low": 2398.5,
        "close": 2403.3,
        "volume": 1200,
    }

    first = client.post("/webhook/tradingview", json=payload)
    second = client.post("/webhook/tradingview", json={**payload, "close": 2404.0})
    status = client.get("/api/status")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["time_utc"] == "2026-05-16T12:30:00Z"
    candles = status.json()["last_candles"]
    assert len(candles) == 1
    assert candles[0]["candle_count"] == 1
    assert candles[0]["last_close"] == 2404.0


def test_webhook_rejects_invalid_symbol_and_naive_timestamp(tmp_path):
    client = TestClient(create_app(tmp_path / "test.sqlite3"))
    base_payload = {
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "time": "2026-05-16T08:30:00-04:00",
        "open": 2400.1,
        "high": 2405.2,
        "low": 2398.5,
        "close": 2403.3,
        "volume": 1200,
    }

    invalid_symbol = client.post("/webhook/tradingview", json={**base_payload, "symbol": "EURUSD"})
    naive_time = client.post("/webhook/tradingview", json={**base_payload, "time": "2026-05-16T08:30:00"})

    assert invalid_symbol.status_code == 422
    assert naive_time.status_code == 422


def test_csv_import_and_analyze_returns_wait_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "test.sqlite3"
    client = TestClient(create_app(db_path))
    start = datetime(2026, 5, 14, tzinfo=timezone.utc)
    imports = [
        ("XAUUSD", "M15", _csv_rows(start, 210)),
        ("XAGUSD", "M15", _csv_rows(start, 210, base=30.0)),
        ("XAUUSD", "H1", _csv_rows(start, 130, step_minutes=60)),
        ("XAUUSD", "H4", _csv_rows(start, 90, step_minutes=240)),
        ("XAUUSD", "D1", _csv_rows(start - timedelta(days=40), 35, step_minutes=1440)),
    ]
    for symbol, timeframe, csv_text in imports:
        response = client.post(
            "/api/import-csv",
            json={"symbol": symbol, "timeframe": timeframe, "csv_text": csv_text},
        )
        assert response.status_code == 200
        assert response.json()["rows_imported"] > 0

    analysis_as_of = (start + timedelta(minutes=15 * 209)).isoformat().replace("+00:00", "Z")
    response = client.post(
        "/api/analyze",
        json={
            "primary_symbol": "XAUUSD",
            "secondary_symbol": "XAGUSD",
            "execution_timeframe": "M15",
            "context_timeframes": ["H4", "H1", "D1"],
            "analysis_as_of": analysis_as_of,
            "mode": "normal",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rule_version"] == "mvp-0.1"
    assert body["action"] in {"WAIT", "BUY", "SELL"}
    assert body["trade_idea"]["action"] == body["action"]
    assert "reason_code" in body["trade_idea"]
    assert "gate_result" in body
    assert "narrative_report" in body

    report = client.post(
        "/api/report",
        json={
            "primary_symbol": "XAUUSD",
            "secondary_symbol": "XAGUSD",
            "execution_timeframe": "M15",
            "context_timeframes": ["H4", "H1", "D1"],
            "analysis_as_of": analysis_as_of,
            "mode": "normal",
        },
    )
    assert report.status_code == 200
    report_body = report.json()
    assert report_body["analysis_as_of"] == body["analysis_as_of"]
    assert report_body["action"] == body["action"]
    assert report_body["reason_code"] == body["trade_idea"]["reason_code"]
    assert report_body["htf_context"] == body["htf_context"]
    assert report_body["confirmation"] == body["confirmation"]
    assert report_body["trade_idea"] == body["trade_idea"]
    assert report_body["selected_dol"] == body["liquidity"]["next_dol"]
    assert report_body["failed_reasons"] == body["gate_result"]["failed_reasons"]
    assert "narrative_report" in report_body

    monkeypatch.setenv("TRADING_STRATEGY_DB_PATH", str(db_path))
    server = importlib.import_module("server")
    assert server.MCP_IMPORT_ERROR is None
    assert server.mcp is not None
    tool_args = {
        "primary_symbol": "XAUUSD",
        "secondary_symbol": "XAGUSD",
        "execution_timeframe": "M15",
        "context_timeframes": ["H4", "H1", "D1"],
        "analysis_as_of": analysis_as_of,
        "mode": "normal",
    }
    mcp_body = server.analyze_market(**tool_args)
    assert mcp_body == body
    assert mcp_body["action"] == body["action"]
    assert mcp_body["trade_idea"] == body["trade_idea"]
    assert mcp_body["htf_context"] == body["htf_context"]
    assert mcp_body["confirmation"] == body["confirmation"]

    mcp_liquidity = server.detect_liquidity(**tool_args)
    assert mcp_liquidity["liquidity"] == body["liquidity"]
    assert mcp_liquidity["dol_candidates"] == body["dol_candidates"]
    assert mcp_liquidity["htf_context"] == body["htf_context"]

    mcp_ssmt = server.detect_ssmt(**tool_args)
    assert mcp_ssmt["ssmt"] == body["ssmt"]

    mcp_trade = server.generate_trade_idea(**tool_args)
    assert mcp_trade["trade_idea"] == body["trade_idea"]
    assert mcp_trade["gate_result"] == body["gate_result"]
    assert mcp_trade["narrative_report"] == body["narrative_report"]


def test_analyze_waits_when_market_data_is_stale(tmp_path):
    client = TestClient(create_app(tmp_path / "test.sqlite3"))
    start = datetime(2026, 5, 14, tzinfo=timezone.utc)
    imports = [
        ("XAUUSD", "M15", _csv_rows(start, 210)),
        ("XAGUSD", "M15", _csv_rows(start, 210, base=30.0)),
        ("XAUUSD", "H1", _csv_rows(start, 130, step_minutes=60)),
        ("XAUUSD", "H4", _csv_rows(start, 90, step_minutes=240)),
        ("XAUUSD", "D1", _csv_rows(start - timedelta(days=40), 35, step_minutes=1440)),
    ]
    for symbol, timeframe, csv_text in imports:
        response = client.post(
            "/api/import-csv",
            json={"symbol": symbol, "timeframe": timeframe, "csv_text": csv_text},
        )
        assert response.status_code == 200

    stale_as_of = (start + timedelta(minutes=15 * 209, days=3)).isoformat().replace("+00:00", "Z")
    response = client.post(
        "/api/analyze",
        json={
            "primary_symbol": "XAUUSD",
            "secondary_symbol": "XAGUSD",
            "execution_timeframe": "M15",
            "context_timeframes": ["H4", "H1", "D1"],
            "analysis_as_of": stale_as_of,
            "mode": "normal",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "WAIT"
    assert body["trade_idea"]["action"] == "WAIT"
    assert body["trade_idea"]["reason_code"] == "STALE_DATA"
    assert body["gate_result"]["passed"] is False
    assert "STALE_DATA" in body["warnings"]
    assert "STALE_XAUUSD_M15" in body["warnings"]


def test_tradingview_analyze_endpoint_returns_live_payload(tmp_path):
    class FakeTradingViewService:
        async def refresh_and_analyze(self, analysis_service):
            return {
                "action": "WAIT",
                "analysis_as_of": "2026-05-18T10:00:00Z",
                "market_data_source": {
                    "provider": "TradingView",
                    "exchange": "OANDA",
                    "series": [{"symbol": "XAUUSD", "timeframe": "M15", "rows_imported": 259}],
                },
            }

    app = create_app(tmp_path / "test.sqlite3")
    app.state.tradingview_service = FakeTradingViewService()
    client = TestClient(app)

    response = client.post("/api/tradingview/analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "WAIT"
    assert body["market_data_source"]["provider"] == "TradingView"


def test_tradingview_analyze_endpoint_maps_fetch_errors(tmp_path):
    class FakeTradingViewService:
        async def refresh_and_analyze(self, analysis_service):
            raise TradingViewFetchError("TradingView unavailable")

    app = create_app(tmp_path / "test.sqlite3")
    app.state.tradingview_service = FakeTradingViewService()
    client = TestClient(app)

    response = client.post("/api/tradingview/analyze")

    assert response.status_code == 502
    assert response.json()["detail"] == "TradingView unavailable"

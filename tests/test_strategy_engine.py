from __future__ import annotations

from datetime import datetime, timedelta, timezone

from strategy import StrategyConfig, analyze_market, normalize_candles
from strategy.ssmt import detect_ssmt
from strategy.swing import detect_swings


def candle(time, open_, high, low, close):
    return {"time": time.isoformat().replace("+00:00", "Z"), "open": open_, "high": high, "low": low, "close": close, "volume": 1}


def make_htf(count: int, minutes: int, start: datetime):
    rows = []
    for i in range(count):
        phase = i % 16
        if phase == 4:
            close = 112
        elif phase == 12:
            close = 68
        else:
            close = 100 + (phase - 8) * 0.7
        if i == count - 1:
            close = 106
        rows.append(candle(start + timedelta(minutes=minutes * i), close - 0.4, close + 1.2, close - 1.2, close))
    return rows


def make_conflicting_h1(count: int, minutes: int, start: datetime):
    rows = []
    for i in range(count):
        phase = i % 16
        if phase == 4:
            close = 140
        elif phase == 12:
            close = 90
        else:
            close = 112 + (phase - 8) * 0.8
        rows.append(candle(start + timedelta(minutes=minutes * i), close - 0.4, close + 1.2, close - 1.2, close))
    return rows


def make_d1(start: datetime):
    rows = []
    for i in range(31):
        close = 100 + (i % 5)
        rows.append(candle(start + timedelta(days=i), close - 1, close + 10, close - 10, close))
    rows[-2] = candle(start + timedelta(days=29), 100, 113, 67, 101)
    rows[-1] = candle(start + timedelta(days=30), 101, 110, 95, 106)
    return rows


def make_bearish_m15(start: datetime, with_mss: bool = True):
    rows = []
    for i in range(210):
        close = 100 + ((i % 10) - 5) * 0.2
        rows.append(candle(start + timedelta(minutes=15 * i), close - 0.1, close + 0.5, close - 0.5, close))
    overrides = {
        187: (101, 102, 99, 100),
        188: (100, 103, 99, 101),
        189: (101, 104, 99, 102),
        190: (102, 108, 100, 101),
        191: (101, 104, 99, 100),
        192: (100, 103, 98, 99),
        193: (99, 103, 99, 100),
        194: (100, 102, 98, 99),
        195: (99, 101, 94, 95),
        196: (95, 101, 96, 99),
        197: (99, 102, 97, 100),
        205: (107, 109, 106.8, 107.5),
        206: (107.5, 107.8, 102, 102.5),
        207: (102, 101.5, 96 if with_mss else 99, 97 if with_mss else 100),
        208: (97 if with_mss else 100, 98 if with_mss else 101, 92 if with_mss else 99, 93 if with_mss else 100),
        209: (93 if with_mss else 100, 96 if with_mss else 101, 92 if with_mss else 99, 94 if with_mss else 100),
    }
    for index, values in overrides.items():
        rows[index] = candle(start + timedelta(minutes=15 * index), *values)
    return rows


def make_secondary_m15(primary):
    rows = []
    for row in primary:
        rows.append({**row, "high": min(row["high"], 104), "low": row["low"] + 0.2, "close": row["close"]})
    return rows


def market(with_mss: bool = True):
    start = datetime(2026, 5, 1, 8, 15, tzinfo=timezone.utc)
    m15 = make_bearish_m15(start, with_mss=with_mss)
    h1_start = start - timedelta(hours=129)
    h4_start = start - timedelta(hours=4 * 89)
    return {
        "XAUUSD": {
            "M15": m15,
            "H1": make_htf(130, 60, h1_start),
            "H4": make_htf(90, 240, h4_start),
            "D1": make_d1(datetime(2026, 4, 1, tzinfo=timezone.utc)),
        },
        "XAGUSD": {"M15": make_secondary_m15(m15)},
    }


def test_detect_swings_finds_local_high_and_low():
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    rows = normalize_candles(
        [
            candle(start + timedelta(minutes=15 * i), price, price + 1, price - 1, price)
            for i, price in enumerate([100, 101, 105, 101, 100, 99, 95, 99, 100])
        ]
    )
    swings = detect_swings(rows, left=2, right=2, timeframe="M15")
    assert [(s.kind, s.price) for s in swings] == [("high", 106.0), ("low", 94.0)]


def test_ssmt_detects_bearish_divergence_when_primary_sweeps_high_and_secondary_fails():
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    primary = normalize_candles(
        [candle(start + timedelta(minutes=15 * i), 100, 101 + i, 99, 100) for i in range(5)]
    )
    secondary = normalize_candles(
        [candle(start + timedelta(minutes=15 * i), 20, 21, 19, 20) for i in range(5)]
    )
    signal = detect_ssmt(primary, secondary, primary[-1].time, StrategyConfig())
    assert signal.available is True
    assert signal.detected is True
    assert signal.type == "bearish"
    assert signal.sync_status == "aligned"


def test_pipeline_all_bearish_confirmations_allows_sell():
    data = market(with_mss=True)
    result = analyze_market(
        data,
        analysis_as_of=data["XAUUSD"]["M15"][-1]["time"],
    )
    assert result["action"] == "SELL"
    assert result["active_model"] == "IRL_TO_ERL_BEARISH"
    assert result["trade_idea"]["reason_code"] == "GATE_COMPLETE"
    assert result["gate_result"]["passed"] is True
    assert result["confirmation"] == {"sweep": True, "displacement": True, "mss": True, "fvg": True}
    assert result["liquidity"]["next_dol"]["score"] >= 60
    assert result["htf_context"]["narrative_status"] == "complete"
    assert result["htf_context"]["narrative_direction"] == "sellside"
    assert result["liquidity"]["next_dol"]["direction"] == "sellside"
    assert result["liquidity"]["next_dol"]["confidence"] == "high"
    assert any("opposite-side buyside sweep" in reason for reason in result["liquidity"]["next_dol"]["reasoning"])
    assert any("MSS confirms direction" in reason for reason in result["liquidity"]["next_dol"]["reasoning"])


def test_pipeline_allows_h1_only_degraded_mode_when_h4_is_missing_and_gate_is_complete():
    data = market(with_mss=True)
    data["XAUUSD"]["H4"] = []
    result = analyze_market(
        data,
        analysis_as_of=data["XAUUSD"]["M15"][-1]["time"],
    )
    assert result["data_coverage"]["status"] == "degraded"
    assert result["data_coverage"]["degraded_mode"] is True
    assert "H4_MISSING" in result["warnings"]
    assert result["htf_context"]["timeframe"] == "H1"
    assert result["htf_context"]["narrative_status"] == "degraded"
    assert result["liquidity"]["next_dol"]["confidence"] == "high"
    assert result["action"] == "SELL"
    assert result["trade_idea"]["reason_code"] == "GATE_COMPLETE"


def test_pipeline_waits_when_mss_is_missing():
    data = market(with_mss=False)
    result = analyze_market(
        data,
        analysis_as_of=data["XAUUSD"]["M15"][-1]["time"],
    )
    assert result["action"] == "WAIT"
    assert result["trade_idea"]["reason_code"] == "MISSING_MSS"
    assert result["gate_result"]["passed"] is False
    assert "mss" in result["trade_idea"]["blocking_conditions"]


def test_pipeline_waits_when_htf_timeframes_conflict_even_if_m15_is_complete():
    data = market(with_mss=True)
    data["XAUUSD"]["H1"] = make_conflicting_h1(
        130,
        60,
        datetime(2026, 4, 25, 23, 15, tzinfo=timezone.utc),
    )
    result = analyze_market(
        data,
        analysis_as_of=data["XAUUSD"]["M15"][-1]["time"],
    )
    assert result["action"] == "WAIT"
    assert result["trade_idea"]["reason_code"] == "HTF_CONFLICT"
    assert result["htf_context"]["conflict"] is True
    assert "HTF_CONFLICT" in result["warnings"]


def test_pipeline_waits_when_required_htf_context_is_insufficient():
    data = market(with_mss=True)
    data["XAUUSD"]["H1"] = data["XAUUSD"]["H1"][:50]
    result = analyze_market(
        data,
        analysis_as_of=data["XAUUSD"]["M15"][-1]["time"],
    )
    assert result["action"] == "WAIT"
    assert result["trade_idea"]["reason_code"] == "MISSING_HTF_CONTEXT"
    assert result["gate_result"]["passed"] is False
    assert "MISSING_HTF_CONTEXT" in result["warnings"]

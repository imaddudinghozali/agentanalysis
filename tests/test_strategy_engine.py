from __future__ import annotations

from datetime import datetime, timedelta, timezone

from strategy import StrategyConfig, analyze_market, normalize_candles
from strategy.common import Candle
from strategy.direction_liquidity import build_direction_liquidity_hierarchy
from strategy.displacement import DisplacementSignal
from strategy.dol import score_dol_candidates
from strategy.liquidity import LiquidityPool
from strategy.ohlc import build_htf_candle_phase
from strategy.range import DealingRange
from strategy.ssmt import detect_ssmt
from strategy.structure import StructureSignal
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


def test_htf_candle_phase_detects_olhc_sequence_from_m15_candles():
    start = datetime(2026, 5, 18, tzinfo=timezone.utc)
    rows = normalize_candles(
        [
            candle(start, 100, 101, 99, 100),
            candle(start + timedelta(minutes=15), 100, 100.5, 95, 96),
            candle(start + timedelta(minutes=30), 96, 106, 96, 105),
            candle(start + timedelta(minutes=45), 105, 105.5, 103, 104),
        ]
    )

    phase = build_htf_candle_phase(rows, rows[-1].time, "D1")

    assert phase is not None
    assert phase.pattern == "OLHC"
    assert phase.current_leg == "high_to_close"
    assert phase.completed_legs == ["open_to_low", "low_to_high"]
    assert phase.low == 95
    assert phase.high == 106


def test_direction_liquidity_hierarchy_prioritizes_daily_to_h1_to_m15_layer():
    data = market(with_mss=True)
    rows = {
        timeframe: normalize_candles(data["XAUUSD"].get(timeframe, []))
        for timeframe in ("M15", "H1", "H4", "D1")
    }

    hierarchy = build_direction_liquidity_hierarchy(
        m15=rows["M15"],
        h1=rows["H1"],
        h4=rows["H4"],
        d1=rows["D1"],
        current_price=rows["M15"][-1].close,
        config=StrategyConfig(),
    )

    assert hierarchy.status == "complete"
    assert hierarchy.active_level is not None
    assert hierarchy.active_level.parent_timeframe == "D1"
    assert hierarchy.active_level.irl_erl_timeframe == "H1"
    assert hierarchy.active_level.direction_timeframes == ["M15", "M5"]
    assert hierarchy.dominant_direction in {"buyside", "sellside", "neutral"}


def test_ssmt_detects_bearish_divergence_when_primary_sweeps_high_and_secondary_fails():
    start = datetime(2026, 5, 1, 5, tzinfo=timezone.utc)
    primary = normalize_candles(
        [
            candle(start, 100, 101, 99, 100),
            candle(start + timedelta(minutes=15), 100, 102, 99, 100),
            candle(start + timedelta(minutes=30), 100, 104, 99, 101),
            candle(start + timedelta(minutes=45), 101, 103, 100, 101),
            candle(start + timedelta(minutes=60), 101, 108, 100, 103),
        ]
    )
    secondary = normalize_candles(
        [
            candle(start, 20, 21, 19, 20),
            candle(start + timedelta(minutes=15), 20, 22, 19, 20),
            candle(start + timedelta(minutes=30), 20, 24, 19, 21),
            candle(start + timedelta(minutes=45), 21, 23, 20, 21),
            candle(start + timedelta(minutes=60), 21, 23.5, 20, 22),
        ]
    )
    signal = detect_ssmt(primary, secondary, primary[-1].time, StrategyConfig())
    assert signal.available is True
    assert signal.detected is True
    assert signal.type == "bearish"
    assert signal.sync_status == "aligned"
    assert signal.quality == "high"
    assert signal.sequence == "sequential"
    assert signal.reference_quarter == "2026-05-01Q1"
    assert signal.primary_quarter == "2026-05-01Q2"


def test_ssmt_rejects_same_quarter_divergence_as_non_sequential():
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    primary = normalize_candles(
        [candle(start + timedelta(minutes=15 * i), 100, 101 + i, 99, 100) for i in range(5)]
    )
    secondary = normalize_candles(
        [candle(start + timedelta(minutes=15 * i), 20, 21, 19, 20) for i in range(5)]
    )

    signal = detect_ssmt(primary, secondary, primary[-1].time, StrategyConfig())

    assert signal.available is True
    assert signal.detected is False
    assert signal.sync_status == "non_sequential_quarter"
    assert signal.sequence == "non_sequential"


def test_ssmt_marks_delivered_divergence_as_magneto_not_active_signal():
    start = datetime(2026, 5, 1, 5, tzinfo=timezone.utc)
    primary = normalize_candles(
        [
            candle(start, 100, 101, 99, 100),
            candle(start + timedelta(minutes=15), 100, 102, 99, 100),
            candle(start + timedelta(minutes=30), 100, 104, 99, 101),
            candle(start + timedelta(minutes=45), 101, 103, 100, 101),
            candle(start + timedelta(minutes=60), 101, 108, 100, 103),
            candle(start + timedelta(minutes=75), 103, 104, 98, 99),
        ]
    )
    secondary = normalize_candles(
        [
            candle(start, 20, 21, 19, 20),
            candle(start + timedelta(minutes=15), 20, 22, 19, 20),
            candle(start + timedelta(minutes=30), 20, 24, 19, 21),
            candle(start + timedelta(minutes=45), 21, 23, 20, 21),
            candle(start + timedelta(minutes=60), 21, 23.5, 20, 22),
            candle(start + timedelta(minutes=75), 22, 23, 19, 20),
        ]
    )

    signal = detect_ssmt(primary, secondary, primary[-1].time, StrategyConfig())

    assert signal.available is True
    assert signal.detected is False
    assert signal.quality == "magneto"
    assert signal.sync_status == "magneto"
    assert signal.magneto is True
    assert signal.magneto_level == 99


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
    assert result["htf_context"]["candle_phase"]["pattern"] in {"OHLC", "OLHC", "UNRESOLVED"}
    assert result["htf_context"]["candle_phase"]["current_leg"]
    assert result["htf_context"]["direction_liquidity"]["active_level"]["parent_timeframe"] == "D1"
    assert result["htf_context"]["narrative_direction"] == "sellside"
    assert result["liquidity"]["next_dol"]["direction"] == "sellside"
    assert result["liquidity"]["next_dol"]["confidence"] == "high"
    assert any("Direction liquidity hierarchy supports this draw" in reason for reason in result["liquidity"]["next_dol"]["reasoning"])
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


def test_dol_scoring_returns_ambiguous_when_opposite_targets_are_close():
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    candles = normalize_candles(
        [candle(start + timedelta(minutes=15 * i), 110, 111, 109, 110) for i in range(20)]
    )
    active_range = DealingRange(
        timeframe="H4",
        high=120,
        low=80,
        high_time=start,
        low_time=start,
        equilibrium=100,
        current_position="equilibrium",
        current_price=110,
        direction_hint="neutral",
    )
    selection = score_dol_candidates(
        [
            LiquidityPool("near_sellside_pool", "H4", "ERL", "sellside", 100),
            LiquidityPool("range_high", "H4", "ERL", "buyside", 120),
        ],
        active_range,
        candles,
        sweeps=[],
        displacement=DisplacementSignal(False),
        structure=StructureSignal(False),
        ssmt=detect_ssmt(candles, candles, candles[-1].time, StrategyConfig()),
        time_context={"killzone": False},
        config=StrategyConfig(),
        htf_direction="sellside",
    )
    assert selection.selected is None
    assert selection.ambiguous is True
    assert selection.reason_code == "DOL_AMBIGUOUS"


def test_live_dol_scoring_prefers_near_fresh_liquidity_over_session_extreme_and_far_macro_target():
    start = datetime(2026, 5, 18, tzinfo=timezone.utc)
    candles = normalize_candles(
        [candle(start + timedelta(minutes=15 * i), 100, 101, 99, 100) for i in range(24)]
    )
    active_range = DealingRange(
        timeframe="H4",
        high=110,
        low=0,
        high_time=start,
        low_time=start,
        equilibrium=55,
        current_position="premium",
        current_price=100,
        direction_hint="sellside",
    )
    selection = score_dol_candidates(
        [
            LiquidityPool("active_range_low", "H4", "ERL", "sellside", 0, "active_range"),
            LiquidityPool("h1_swing_low", "H1", "IRL", "sellside", 97, "swing"),
            LiquidityPool("current_day_low", "M15", "ERL", "sellside", 96, "current_day"),
        ],
        active_range,
        candles,
        sweeps=[],
        displacement=DisplacementSignal(False),
        structure=StructureSignal(False),
        ssmt=detect_ssmt(candles, candles, candles[-1].time, StrategyConfig()),
        time_context={"killzone": False},
        config=StrategyConfig(),
        htf_direction="sellside",
        prefer_actionable_targets=True,
    )

    assert selection.selected is not None
    assert selection.selected.label == "h1_swing_low"
    assert selection.candidates[-1].label == "active_range_low"
    current_day_candidate = next(candidate for candidate in selection.candidates if candidate.label == "current_day_low")
    assert any("not fresh liquidity" in reason for reason in current_day_candidate.reasoning)


def test_ssmt_timestamp_mismatch_is_unavailable_and_warns():
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    primary = normalize_candles(
        [candle(start + timedelta(minutes=15 * i), 100, 101 + i, 99, 100) for i in range(5)]
    )
    secondary = normalize_candles(
        [candle(start + timedelta(minutes=15 * i + 5), 20, 21, 19, 20) for i in range(5)]
    )
    signal = detect_ssmt(primary, secondary, primary[-1].time, StrategyConfig())
    assert signal.available is False
    assert signal.detected is False
    assert signal.sync_status == "timestamp_mismatch"
    assert signal.warning == "SSMT_TIMESTAMP_MISMATCH"


def test_pipeline_missing_d1_keeps_analysis_but_disables_previous_day_dol_candidates():
    data = market(with_mss=True)
    data["XAUUSD"]["D1"] = []
    result = analyze_market(
        data,
        analysis_as_of=data["XAUUSD"]["M15"][-1]["time"],
    )
    assert "D1_MISSING" in result["warnings"]
    assert result["data_coverage"]["status"] == "complete"
    assert all(not candidate["label"].startswith("previous_day") for candidate in result["dol_candidates"])


def test_pipeline_waits_when_current_price_is_outside_active_dealing_range():
    data = market(with_mss=True)
    rows = data["XAUUSD"]["M15"]
    _set_index = -1
    last_time = datetime.fromisoformat(rows[_set_index]["time"].replace("Z", "+00:00"))
    rows[_set_index] = candle(last_time, 200, 201, 199, 200)
    data["XAGUSD"]["M15"] = make_secondary_m15(rows)
    result = analyze_market(
        data,
        analysis_as_of=rows[-1]["time"],
    )
    assert result["action"] == "WAIT"
    assert result["trade_idea"]["reason_code"] == "NO_ACTIVE_DEALING_RANGE"
    assert result["gate_result"]["passed"] is False

RULE_VERSION = "mvp-0.1"

DEFAULT_PARAMS = {
    "swing_left_bars_m15": 2,
    "swing_right_bars_m15": 2,
    "swing_left_bars_h1": 3,
    "swing_right_bars_h1": 3,
    "swing_left_bars_h4": 3,
    "swing_right_bars_h4": 3,
    "swing_left_bars_d1": 2,
    "swing_right_bars_d1": 2,
    "equal_high_low_tolerance_pct": 0.05,
    "sweep_buffer_ticks": 0.1,
    "ssmt_alignment_tolerance_minutes": 1,
    "secondary_stale_after_minutes": 15,
    "displacement_body_atr_multiplier": 1.5,
    "fvg_min_size_ticks": 0.1,
    "equilibrium_band_pct": 5,
    "minimum_htf_candles_h1": 120,
    "minimum_htf_candles_h4": 80,
    "minimum_htf_candles_d1": 30,
}

CRITICAL_WARNINGS = {
    "MISSING_HTF_CONTEXT",
    "INSUFFICIENT_DATA",
    "STALE_DATA",
    "HTF_CONFLICT",
    "DOL_AMBIGUOUS",
}


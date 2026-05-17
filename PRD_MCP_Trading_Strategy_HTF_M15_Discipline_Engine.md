# PRD - MCP Trading Strategy Discipline Engine

## 1. Product Summary

This product helps XAUUSD ICT/SMC traders avoid premature entries by turning higher-timeframe context and M15 execution signals into an auditable WAIT/BUY/SELL decision. It does not try to be a signal bot. Its main job is to show whether a setup is valid, incomplete, conflicting, invalidated, or should remain WAIT.

Internal tagline:

```text
HTF context, M15 execution, WAIT-first discipline engine.
```

The system reads market OHLC data, builds higher-timeframe context, detects liquidity behavior, compares XAUUSD with XAGUSD for SSMT, and outputs structured JSON plus a narrative explanation that an AI agent or dashboard can consume. MCP is an integration layer, not the product promise.

Primary market:
- XAUUSD

SSMT comparison market:
- XAGUSD

Optional future confirmation:
- DXY

## 1.1 Product Promise And Non-Promise

Product promise:
- Show what is confirmed, missing, conflicting, or invalidated before a trader enters.
- Make WAIT feel justified, not like uncertainty.
- Explain why the selected DOL beat alternative liquidity targets.
- Give AI agents and dashboards the same deterministic engine output.

Product non-promise:
- Does not predict profit.
- Does not guarantee win rate.
- Does not provide personalized financial advice.
- Does not replace trader judgment or risk management.
- Does not execute trades.

Trust boundary:
- Confidence means rule completeness and data quality, not probability of trade success.
- BUY or SELL means setup conditions are complete according to the configured model, not that the trade will win.
- Narrative text must never decide anything. Narrative only explains deterministic engine output.

## 2. Conversation Summary And Product Direction

The original PRD proposed a full MCP trading strategy engine with TradingView webhook, CSV fallback, backend strategy engine, frontend dashboard, and MCP tools.

From product review:
- The project should not be positioned as a buy/sell signal bot.
- The stronger wedge is a strategy debugger or discipline engine.
- The product earns trust by saying WAIT when confirmation is incomplete.
- The first product promise is not profit, but structured reasoning and reduced impulsive entries.

From engineering review:
- The system should be deterministic first, with clear rule outputs.
- The frontend should not contain trading logic.
- MCP should expose the same analysis engine used by the API and dashboard.
- Tests and golden fixtures are essential because discretionary trading rules can easily sound correct while being inconsistent.

From CEO review correction:
- M15-only is not enough.
- HTF context is mandatory because DOL, IRL, ERL, premium, and discount cannot be reliably inferred from M15 alone.
- The correct MVP is multi-timeframe for context, but single-timeframe for execution.

Final direction:

```text
HTF determines bias and DOL.
M15 determines whether a setup is executable or WAIT.
```

## 3. Product Positioning

### 3.1 What This Product Is

This product is a trading setup analysis and discipline engine for ICT/SMC workflows.

It helps answer:
1. What is the higher-timeframe draw on liquidity?
2. Is price in premium, discount, or equilibrium relative to the active range?
3. What liquidity has recently been taken?
4. Is the current move IRL to ERL, ERL to IRL, or liquidity to liquidity?
5. Does M15 confirm or conflict with the higher-timeframe story?
6. Is SSMT present between XAUUSD and XAGUSD?
7. Has displacement appeared?
8. Has MSS or CHOCH appeared?
9. Is there a valid FVG entry model?
10. Should the action be WAIT, BUY, or SELL?

### 3.2 What This Product Is Not

This product is not:
- An auto-trading bot.
- A guaranteed signal service.
- A broker execution system.
- A full backtesting platform in MVP.
- A TradingView browser automation system in MVP.
- A news-aware discretionary replacement.

## 4. Target User

Primary user:
- A discretionary ICT/SMC XAUUSD trader who already understands liquidity, DOL, premium/discount, MSS, FVG, and SSMT, but wants a disciplined second opinion before entry.

User pain:
- The trader sees a possible setup but enters too early.
- The trader reads M15 confirmation without checking HTF DOL.
- The trader confuses local liquidity with real external liquidity.
- The trader wants an AI agent to explain the setup in consistent language.

Excluded user:
- Beginner traders looking for simple buy/sell signals.
- Users who expect automated execution.
- Traders outside the XAUUSD/XAGUSD workflow in MVP.
- Users looking for P/L tracking, risk sizing, journaling, or strategy optimization in MVP.

Primary user outcome:

```text
The trader can see what is confirmed, what is missing, what is invalidated,
and why WAIT may be the correct action.
```

## 4.1 Primary Workflow

1. Trader loads or streams XAUUSD/XAGUSD candles.
2. System builds HTF context.
3. System evaluates M15 execution.
4. Trader sees action, DOL, confirmed evidence, missing evidence, conflict, and invalidation.
5. If incomplete, system explains why WAIT is required.

## 5. Core Product Thesis

The product becomes useful when it behaves like a disciplined checklist operator, not like an aggressive signal generator.

Important product rule:

```text
WAIT is a first-class output.
```

A BUY or SELL may only be produced when higher-timeframe context and M15 execution logic align with enough confirmation.

Final product principle:

```text
The product should feel valuable even when it says WAIT.
If users only value BUY/SELL, the product has failed its positioning.
```

## 6. MVP Scope

### 6.1 MVP In Scope

MVP must include:
- TradingView webhook endpoint for candle ingestion.
- CSV import fallback for testing and fixture loading.
- SQLite candle storage.
- XAUUSD primary symbol.
- XAGUSD secondary symbol for SSMT.
- HTF context from required H1 + H4 XAUUSD candles, with D1 used for PDH/PDL when available.
- M15 execution analysis.
- Swing high and swing low detection.
- Dealing range detection.
- Premium, discount, equilibrium calculation.
- HTF IRL and ERL mapping.
- DOL candidate scoring.
- Liquidity sweep detection.
- SSMT detection between XAUUSD and XAGUSD.
- Displacement detection.
- MSS or CHOCH detection.
- FVG detection.
- Trade idea generation with strict WAIT gating.
- Narrative report generation.
- MCP tools for AI agents.
- Minimal dashboard for analysis visibility.

### 6.1.1 HTF Data Requirements

| Data | Required | Minimum Candles | Degraded Behavior |
|---|---:|---:|---|
| XAUUSD M15 | Yes | 200 | Cannot analyze without it |
| XAUUSD H1 | Yes | 120 | WAIT if missing |
| XAUUSD H4 | Yes for normal mode | 80 | H1-only degraded mode |
| XAUUSD D1 | Optional but recommended | 30 | Disable PDH/PDL DOL candidates |
| XAGUSD M15 | Required for SSMT models | 200 | Mark SSMT unavailable |
| XAGUSD H1/H4 | Not MVP | N/A | Do not use for HTF bias |

Degraded H1-only mode:
- Allowed only when XAUUSD H1 and M15 are complete but H4 is missing.
- Must set `data_coverage.degraded_mode = true`.
- Must return WAIT unless selected DOL confidence is high and the trade gate is complete.
- Must include a warning that H4 context is unavailable.

### 6.2 MVP Out Of Scope

MVP will not include:
- Auto trade execution.
- Broker order placement.
- Full TradingView browser automation.
- Auto drawing on TradingView charts.
- Full historical backtest engine.
- Machine learning model.
- News API.
- DXY confirmation.
- Full M5 refinement.
- Advanced order block scoring.
- Profit/loss tracking.
- Risk sizing.
- Trade journaling.
- Strategy optimization.
- Multi-symbol scanning.
- Alert recommendations beyond the current analyzed market.

## 7. Multi-Timeframe Strategy Model

### 7.1 Timeframe Roles

```text
Daily / H4 / H1:
  - Build macro context.
  - Identify major range.
  - Identify premium, discount, equilibrium.
  - Identify major IRL and ERL.
  - Determine likely DOL.

M15:
  - Detect execution sweep.
  - Detect SSMT behavior.
  - Detect displacement.
  - Detect MSS or CHOCH.
  - Detect FVG entry area.
  - Decide WAIT, BUY, or SELL.

M5:
  - Deferred.
  - Future refinement for precision entry.
```

### 7.2 Core Rule

HTF context determines directional permission.
M15 determines execution permission.

Examples:
- If HTF DOL is buyside and M15 shows bullish confirmation, BUY may be allowed.
- If HTF DOL is buyside but M15 shows bearish local sweep, action should usually be WAIT unless the system can explain a valid counter-context model.
- If M15 gives a sell but HTF is in discount targeting buyside ERL, the system should avoid SELL or mark the setup as counter-context.

## 7.3 Deterministic Detection Parameters

Default parameters must be configurable, but MVP tests should use these values:

| Parameter | Default |
|---|---:|
| swing_left_bars_m15 | 2 |
| swing_right_bars_m15 | 2 |
| swing_left_bars_h1 | 3 |
| swing_right_bars_h1 | 3 |
| swing_left_bars_h4 | 3 |
| swing_right_bars_h4 | 3 |
| swing_left_bars_d1 | 2 |
| swing_right_bars_d1 | 2 |
| equal_high_low_tolerance_pct | 0.05 |
| sweep_buffer_ticks | 0.1 |
| ssmt_alignment_tolerance_minutes | 1 |
| secondary_stale_after_minutes | 15 |
| displacement_body_atr_multiplier | 1.5 |
| fvg_min_size_ticks | 0.1 |
| equilibrium_band_pct | 5 |
| minimum_htf_candles_h1 | 120 |
| minimum_htf_candles_h4 | 80 |
| minimum_htf_candles_d1 | 30 |

Swing high:
- A candle is a swing high when its high is greater than the highs of N candles to the left and N candles to the right.

Swing low:
- A candle is a swing low when its low is lower than the lows of N candles to the left and N candles to the right.

Major swing filters:

| Timeframe | Swing Left | Swing Right | Major Swing Filter |
|---|---:|---:|---|
| M15 | 2 | 2 | min 0.25 ATR distance |
| H1 | 3 | 3 | min 0.35 ATR distance |
| H4 | 3 | 3 | min 0.50 ATR distance |
| D1 | 2 | 2 | min 0.50 ATR distance |

Active dealing range:
- Active dealing range is the most recent HTF impulse range whose high and low contain current price.
- Prefer H4 range over H1 when both are valid.
- If no containing H4 range exists, use H1.
- If no active range exists, return WAIT with reason `NO_ACTIVE_DEALING_RANGE`.

Last closed candle rule:
- Analysis must use only candles closed at or before `analysis_as_of`.
- If `analysis_as_of` is before the latest candle close, ignore later/incomplete candles.

## 8. Core Concepts

### 8.1 IRL - Internal Range Liquidity

Internal liquidity includes:
- Minor swing highs.
- Minor swing lows.
- Equal highs inside the active range.
- Equal lows inside the active range.
- Internal FVGs.
- Session highs or lows inside the larger range.

IRL is often used for retracement, manipulation, or rebalance.

### 8.2 ERL - External Range Liquidity

External liquidity includes:
- Previous day high.
- Previous day low.
- Previous week high.
- Previous week low.
- Major swing high.
- Major swing low.
- Large equal highs.
- Large equal lows.

ERL is a stronger target candidate than most local M15 levels.

### 8.3 DOL - Draw On Liquidity

DOL is the most logical liquidity target based on current context.

DOL must not be a vague label. It must be computed and explained.

DOL inputs:
- HTF premium or discount.
- Active dealing range.
- Liquidity recently taken.
- Available IRL and ERL pools.
- Session timing.
- SSMT confirmation.
- Displacement direction.
- Market structure.
- Distance to target.
- Liquidity quality.

### 8.4 SSMT

SSMT is used as manipulation confirmation, not as a standalone entry.

Bullish SSMT:
- XAUUSD makes a lower low.
- XAGUSD fails to make a lower low.
- Interpretation: possible sellside sweep on XAUUSD.

Bearish SSMT:
- XAUUSD makes a higher high.
- XAGUSD fails to make a higher high.
- Interpretation: possible buyside sweep on XAUUSD.

## 9. DOL Scoring Formula

Each DOL candidate must receive a deterministic score and explanation. The initial MVP score uses 100 possible points before proximity penalty.

| Factor | Points | Rule |
|---|---:|---|
| liquidity_type | 0-20 | ERL 20, IRL 10, weak internal level 5 |
| htf_location | 0-20 | Premium favors sellside, discount favors buyside, equilibrium max 5 |
| range_alignment | 0-15 | Target sits outside active range or at strong range boundary |
| recent_opposite_sweep | 0-15 | Opposite-side sweep within last 16 M15 candles |
| displacement | 0-10 | Candle body >= 1.5x ATR body average in DOL direction |
| structure | 0-10 | MSS/CHOCH confirms DOL direction |
| ssmt | 0-5 | SSMT confirms manipulation direction |
| session | 0-5 | London/NY killzone or active expansion window |
| proximity_penalty | 0 to -15 | Penalize targets that are too far relative to current ATR |

Confidence:

| Score | Confidence |
|---:|---|
| 80-100 | high |
| 60-79 | medium |
| 40-59 | low |
| <40 | unavailable |

DOL tie-breakers:
1. Prefer ERL over IRL.
2. Prefer target aligned with H4 over H1.
3. Prefer nearer target only if scores are within 10 points.
4. If top two DOL candidates are within 5 points but opposite direction, return WAIT with reason `DOL_AMBIGUOUS`.

BUY/SELL may not be emitted when selected DOL score is below 60.

Example output:

```json
{
  "selected_dol": {
    "level": 2390.0,
    "label": "previous_day_low",
    "liquidity_type": "ERL",
    "direction": "sellside",
    "score": 82,
    "confidence": "high",
    "reasoning": [
      "HTF price is trading in premium",
      "Internal buyside liquidity was swept on M15",
      "Bearish SSMT appeared between XAUUSD and XAGUSD",
      "Previous day low is the strongest external sellside pool"
    ]
  }
}
```

## 10. WAIT-First Trade Idea Gate

The trade idea engine must default to WAIT.

BUY or SELL requires enough confirmation.

### 10.1 Required Gate Inputs

Inputs:
- HTF DOL direction.
- HTF price location.
- M15 sweep.
- M15 SSMT status.
- M15 displacement.
- M15 MSS or CHOCH.
- M15 FVG.
- Invalidation level.

### 10.2 Decision And Reason Code Taxonomy

Action enum:
- WAIT
- BUY
- SELL

Reason code enum:
- MISSING_HTF_CONTEXT
- NO_ACTIVE_DEALING_RANGE
- UNCLEAR_DOL
- DOL_AMBIGUOUS
- HTF_CONFLICT
- HTF_M15_CONFLICT
- MISSING_SWEEP
- MISSING_SSMT
- SSMT_UNAVAILABLE
- MISSING_DISPLACEMENT
- MISSING_MSS
- MISSING_FVG
- MISSING_INVALIDATION
- STALE_DATA
- INSUFFICIENT_DATA
- GATE_COMPLETE

Output `trade_idea` must include:

```json
{
  "action": "WAIT",
  "reason_code": "MISSING_MSS",
  "blocking_conditions": ["mss"]
}
```

### 10.3 Trade Gate Matrix

| Model | HTF Requirement | M15 Requirement | SSMT | Action Allowed |
|---|---|---|---|---|
| `IRL_TO_ERL_BULLISH` | Discount or bullish HTF DOL | Sellside sweep + bullish displacement + bullish MSS + bullish FVG | Optional | BUY |
| `IRL_TO_ERL_BEARISH` | Premium or bearish HTF DOL | Buyside sweep + bearish displacement + bearish MSS + bearish FVG | Optional | SELL |
| `SSMT_REVERSAL_BULLISH` | HTF DOL buyside or neutral | Sellside sweep + bullish SSMT + bullish displacement + bullish MSS | Required | BUY |
| `SSMT_REVERSAL_BEARISH` | HTF DOL sellside or neutral | Buyside sweep + bearish SSMT + bearish displacement + bearish MSS | Required | SELL |
| `CONTEXT_CONFLICT` | HTF and M15 disagree | Any local confirmation | Any | WAIT |
| `NO_DOL` | DOL unavailable or ambiguous | Any | Any | WAIT |

Hard BUY/SELL gate:
- `selected_dol.score >= 60`.
- `active_model` is not null.
- Invalidation price is present.
- No critical data warnings are present.
- Required confirmations for the active model are present.

Critical data warnings:
- MISSING_HTF_CONTEXT
- INSUFFICIENT_DATA
- STALE_DATA
- SSMT_UNAVAILABLE when active model requires SSMT
- HTF_CONFLICT
- DOL_AMBIGUOUS

SSMT rule:
- SSMT is required for `SSMT_REVERSAL_*` models.
- SSMT is optional for `IRL_TO_ERL_*` models, but unavailable SSMT must still be visible in the output.

Equilibrium rule:
- Price inside the equilibrium band returns WAIT unless DOL score is high (`>= 80`) and all required gate confirmations are present.

## 11. Data Flow

```text
TradingView Alert / CSV Import
        |
        v
Payload Validation
        |
        v
SQLite Candle Store
        |
        v
Market Data Loader
        |
        +--> HTF Context Engine
        |       - Daily/H4/H1 range
        |       - premium/discount
        |       - IRL/ERL map
        |       - DOL candidates
        |
        +--> M15 Execution Engine
                - sweep
                - SSMT
                - displacement
                - MSS/CHOCH
                - FVG
        |
        v
Trade Idea Gate
        |
        +--> JSON analysis
        +--> Narrative report
        +--> MCP tool response
        +--> Dashboard response
```

## 12. Backend Requirements

### 12.1 Tech Stack

- Python 3.11+
- FastAPI
- Pydantic
- Pandas
- NumPy
- SQLite
- MCP Python SDK
- Pytest

### 12.2 Recommended Folder Structure

```text
trading-strategy-mcp/
  app.py
  server.py
  requirements.txt
  README.md
  data/
    fixtures/
      xauusd_m15_sample.csv
      xagusd_m15_sample.csv
      xauusd_h1_sample.csv
      xauusd_h4_sample.csv
  storage/
    database.py
    candles.py
  schemas/
    candle.py
    market.py
    liquidity.py
    analysis.py
    trade.py
  services/
    ingestion_service.py
    analysis_service.py
    report_service.py
  strategy/
    pipeline.py
    time_context.py
    swing.py
    range.py
    liquidity.py
    dol.py
    ssmt.py
    displacement.py
    structure.py
    fvg.py
    trade_idea.py
    narrative.py
  tests/
    fixtures/
    test_ingestion.py
    test_htf_context.py
    test_liquidity.py
    test_dol.py
    test_ssmt.py
    test_trade_idea.py
    test_api.py
```

## 13. API Requirements

### 13.1 POST /webhook/tradingview

Receives one candle from TradingView.

Input:

```json
{
  "symbol": "XAUUSD",
  "timeframe": "M15",
  "time": "2026-05-16T08:30:00-04:00",
  "open": 2400.1,
  "high": 2405.2,
  "low": 2398.5,
  "close": 2403.3,
  "volume": 1200
}
```

Rules:
- Validate symbol.
- Validate timeframe.
- Normalize timestamp to UTC.
- Upsert candle by symbol, timeframe, and time.
- Return ingestion status.

### 13.2 POST /api/import-csv

Imports CSV candles for testing or backfill.

Required columns:

```text
time,open,high,low,close,volume
```

### 13.3 POST /api/analyze

`analysis_as_of` is required so fixture tests and replay analysis are reproducible. The engine must only use candles closed at or before this timestamp.

Input:

```json
{
  "primary_symbol": "XAUUSD",
  "secondary_symbol": "XAGUSD",
  "execution_timeframe": "M15",
  "context_timeframes": ["H4", "H1", "D1"],
  "analysis_as_of": "2026-05-16T13:30:00Z",
  "mode": "normal"
}
```

Output:
- Full analysis JSON.
- Narrative report.
- Latest trade idea.

### 13.4 GET /api/status

Returns:
- Last candle per symbol/timeframe.
- Data freshness.
- Missing timeframe warnings.
- SSMT availability.

## 14. MCP Tools

MCP is not the product promise. MCP allows AI agents to query the same deterministic analysis used by the API and dashboard. MCP tools must call the shared analysis service and must not implement separate trading logic.

### 14.1 analyze_market

Returns full market state.

Input:

```json
{
  "primary_symbol": "XAUUSD",
  "secondary_symbol": "XAGUSD",
  "execution_timeframe": "M15",
  "context_timeframes": ["H4", "H1", "D1"],
  "analysis_as_of": "2026-05-16T13:30:00Z",
  "mode": "normal"
}
```

### 14.2 detect_liquidity

Returns HTF and M15 liquidity pools, taken liquidity, and next DOL candidates.

### 14.3 detect_ssmt

Returns SSMT status, type, quality, divergence point, and data sync status.

### 14.4 generate_trade_idea

Returns WAIT, BUY, or SELL with entry area, invalidation, and reasoning.

## 15. Database Requirements

### 15.1 candles

```sql
CREATE TABLE candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    time_utc DATETIME NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL,
    source TEXT NOT NULL DEFAULT 'webhook',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timeframe, time_utc)
);
```

### 15.2 analysis_history

```sql
CREATE TABLE analysis_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_symbol TEXT NOT NULL,
    secondary_symbol TEXT,
    execution_timeframe TEXT NOT NULL,
    context_timeframes TEXT NOT NULL,
    analysis_as_of DATETIME NOT NULL,
    rule_version TEXT NOT NULL,
    active_model TEXT,
    bias TEXT,
    action TEXT,
    dol_label TEXT,
    confidence TEXT,
    data_coverage_json TEXT NOT NULL,
    gate_result_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 15.2.1 rule_runs

```sql
CREATE TABLE rule_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL,
    rule_version TEXT NOT NULL,
    selected_dol_score INTEGER,
    active_model TEXT,
    gate_passed BOOLEAN NOT NULL,
    failed_reasons TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 15.3 uploaded_files

```sql
CREATE TABLE uploaded_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    file_path TEXT NOT NULL,
    rows_imported INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 16. Output Analysis Schema

```json
{
  "primary_symbol": "XAUUSD",
  "secondary_symbol": "XAGUSD",
  "execution_timeframe": "M15",
  "context_timeframes": ["H4", "H1", "D1"],
  "analysis_as_of": "2026-05-16T13:30:00Z",
  "rule_version": "mvp-0.1",
  "market_state": "post_sweep_displacement",
  "active_model": "IRL_TO_ERL",
  "bias": "SELL",
  "action": "WAIT",
  "data_coverage": {
    "status": "complete",
    "missing": [],
    "stale": [],
    "degraded_mode": false
  },
  "time_context": {
    "session": "New York",
    "killzone": true,
    "valid_time": true
  },
  "htf_context": {
    "dealing_range_high": 2435.2,
    "dealing_range_low": 2388.1,
    "equilibrium": 2411.65,
    "current_position": "premium",
    "dol_direction": "sellside"
  },
  "liquidity": {
    "recently_taken": [
      {
        "label": "internal_buyside_liquidity",
        "timeframe": "M15",
        "price": 2432.1
      }
    ],
    "next_dol": {
      "label": "previous_day_low",
      "timeframe": "D1",
      "liquidity_type": "ERL",
      "price": 2390.0,
      "score": 82
    }
  },
  "dol_candidates": [
    {
      "label": "previous_day_low",
      "timeframe": "D1",
      "liquidity_type": "ERL",
      "direction": "sellside",
      "price": 2390.0,
      "score": 82,
      "confidence": "high"
    }
  ],
  "ssmt": {
    "available": true,
    "detected": true,
    "type": "bearish",
    "quality": "medium",
    "sync_status": "aligned"
  },
  "confirmation": {
    "sweep": true,
    "displacement": true,
    "mss": false,
    "fvg": true
  },
  "trade_idea": {
    "action": "WAIT",
    "reason_code": "MISSING_MSS",
    "blocking_conditions": ["mss"],
    "reason_wait": "Bearish HTF and M15 sweep are aligned, but MSS confirmation is missing.",
    "entry_model": null,
    "entry_area": null,
    "stop_loss": null,
    "take_profit": 2390.0,
    "invalidation": "MSS required before entry model becomes valid"
  },
  "gate_result": {
    "passed": false,
    "failed_reasons": ["MISSING_MSS"],
    "required_confirmations": ["sweep", "displacement", "mss", "fvg"],
    "present_confirmations": ["sweep", "displacement", "fvg"]
  },
  "confidence": "medium",
  "reasoning": [
    "HTF price is trading in premium",
    "HTF DOL points toward external sellside liquidity",
    "M15 swept internal buyside liquidity",
    "Bearish SSMT detected between XAUUSD and XAGUSD",
    "MSS has not confirmed, so action remains WAIT"
  ],
  "warnings": []
}
```

## 17. Frontend Requirements

The MVP dashboard should be minimal and should not become the center of the system.

Dashboard panels:
- Data status.
- HTF context.
- DOL candidate.
- M15 confirmation checklist.
- SSMT panel.
- Trade idea panel.
- Narrative report.

The dashboard must clearly show missing confirmation.

Every analysis must make these trust signals visible:
- HTF bias source.
- Selected DOL and runner-up DOL.
- Why selected DOL beat alternatives.
- M15 confirmations present.
- M15 confirmations missing.
- Whether SSMT was detected, unavailable, or not required.
- Invalidation level or reason invalidation is unavailable.
- Data coverage and degraded-mode status.

Example UI priority:

```text
Action: WAIT
Reason: MSS missing
HTF DOL: Previous Day Low
M15: Buyside sweep + bearish SSMT + displacement
Missing: MSS confirmation
```

## 18. Data Sync Rules

### 18.1 SSMT Candle Alignment

XAUUSD and XAGUSD must be aligned before SSMT can be evaluated.

Possible states:
- aligned
- secondary_missing
- secondary_stale
- timestamp_mismatch
- insufficient_data

If SSMT is unavailable:
- The system must not silently ignore it.
- The result must include a warning.
- Trade idea should usually remain WAIT if SSMT is required for the model.

SSMT mismatch behavior:
- XAGUSD timestamp mismatch greater than `ssmt_alignment_tolerance_minutes` sets `sync_status = timestamp_mismatch`.
- Stale XAGUSD sets `sync_status = secondary_stale`.
- The engine must not infer SSMT from stale or mismatched secondary data.

### 18.2 Timezone Rules

All candle times must be normalized to UTC.

The system must still support session logic in New York time.

Session outputs:
- Asia
- London
- New York
- NY Killzone
- Outside major session

## 18.3 Edge Case Expected Behavior

| Edge Case | Required Behavior |
|---|---|
| Equal-score DOL candidates | Choose ERL over IRL, then H4-aligned target, then nearer target if scores are within 10 points |
| Opposite-direction DOL candidates within 5 points | WAIT with `DOL_AMBIGUOUS` |
| Missing D1 but H4/H1 present | Allow analysis with warning `D1_MISSING`; disable PDH/PDL candidates |
| Missing H1 | WAIT with `MISSING_HTF_CONTEXT` |
| H4 missing but H1 present | Run degraded mode; require WAIT unless high-confidence DOL and complete gate |
| Price inside equilibrium band | WAIT unless DOL score >= 80 and gate is complete |
| Conflicting HTF timeframes | WAIT with `HTF_CONFLICT` |
| Analysis time before latest candle close | Use last closed candle only |
| Current price outside active range | Recompute range; if no valid range, WAIT |

## 19. Acceptance Criteria

The MVP is complete when:

1. Backend can ingest TradingView webhook candles.
2. Backend can import CSV data for XAUUSD and XAGUSD.
3. Candle data is stored in SQLite with duplicate protection.
4. HTF context can be built from Daily, H4, and/or H1 data.
5. M15 execution context can be analyzed.
6. System can detect swing highs and swing lows.
7. System can build dealing range.
8. System can calculate premium, discount, and equilibrium.
9. System can classify IRL and ERL.
10. System can detect liquidity sweeps.
11. System can detect SSMT and explain sync status.
12. System can detect displacement.
13. System can detect MSS or CHOCH.
14. System can detect FVG.
15. System can score DOL candidates.
16. System can generate WAIT, BUY, or SELL with strict gating.
17. WAIT output includes the missing confirmation reason.
18. MCP tools expose the same engine output as the API.
19. Dashboard displays HTF context, M15 confirmation, DOL, SSMT, and trade idea.
20. README explains how to run backend, MCP server, frontend, webhook, and CSV import.

MVP testable complete when:
- All unit tests pass.
- All golden fixture tests pass.
- Each WAIT fixture returns the expected `reason_code`.
- BUY/SELL is never returned when any required gate input is false.
- API and MCP outputs are byte-equivalent after removing transport metadata.
- Re-running the same fixture with the same `analysis_as_of` returns identical JSON.
- In 20 labeled real setup examples, the system identifies the same HTF DOL direction as the trader in at least 70% of cases.
- No BUY/SELL is emitted when HTF context is unavailable.

## 20. Test Plan

### 20.1 Unit Tests

Required tests:
- CSV validation.
- Candle upsert.
- Swing high and swing low detection.
- Dealing range calculation.
- Premium, discount, equilibrium.
- IRL and ERL classification.
- Sweep detection.
- SSMT detection.
- SSMT missing data states.
- Displacement detection.
- MSS/CHOCH detection.
- FVG detection.
- DOL scoring.
- WAIT gating.
- Reason code selection.
- Gate result present/failed confirmation lists.

### 20.2 Integration Tests

Required flows:
- CSV import -> candle store -> analysis.
- Webhook -> candle store -> analysis.
- XAUUSD/XAGUSD aligned data -> SSMT available.
- XAUUSD without XAGUSD -> SSMT unavailable warning.
- HTF bearish DOL + M15 bearish confirmation -> SELL allowed only after gate completion.
- HTF bullish DOL + M15 bearish local signal -> WAIT due to context conflict.

### 20.3 Golden Fixtures

Golden fixtures must be oracle-driven. Each fixture must define expected action, expected active model, expected DOL, expected reason code, expected warnings, and required confirmations.

Required fixture cases:

1. `bearish_complete_model_001` -> expected `SELL`, reason code `GATE_COMPLETE`.
2. `bullish_complete_model_001` -> expected `BUY`, reason code `GATE_COMPLETE`.
3. `bearish_missing_mss_001` -> expected `WAIT`, reason code `MISSING_MSS`.
4. `bullish_missing_displacement_001` -> expected `WAIT`, reason code `MISSING_DISPLACEMENT`.
5. `htf_bullish_m15_bearish_conflict_001` -> expected `WAIT`, reason code `HTF_M15_CONFLICT`.
6. `equilibrium_unclear_dol_001` -> expected `WAIT`, reason code `UNCLEAR_DOL`.
7. `missing_xagusd_required_ssmt_001` -> expected `WAIT`, warning `SSMT_UNAVAILABLE`.
8. `secondary_stale_001` -> expected `WAIT`, warning `SECONDARY_STALE`.
9. `insufficient_htf_001` -> expected `WAIT`, warning `INSUFFICIENT_HTF_DATA`.
10. `duplicate_webhook_001` -> expected one stored candle after duplicate upsert.

### 20.4 Fixture Manifest

Each scenario in `tests/fixtures/` must include `manifest.json`.

```json
{
  "fixture_id": "bearish_complete_model_001",
  "symbols": ["XAUUSD", "XAGUSD"],
  "timeframes": ["D1", "H4", "H1", "M15"],
  "analysis_as_of": "2026-05-16T14:45:00Z",
  "expected_action": "SELL",
  "expected_bias": "SELL",
  "expected_active_model": "IRL_TO_ERL_BEARISH",
  "expected_dol_label": "previous_day_low",
  "expected_reason_code": "GATE_COMPLETE",
  "required_confirmations": {
    "m15_buyside_sweep": true,
    "bearish_ssmt": true,
    "bearish_displacement": true,
    "bearish_mss": true,
    "bearish_fvg": true
  },
  "expected_warnings": []
}
```

### 20.5 Required JSON Assertions

Each golden fixture must assert at least:

```text
$.action
$.bias
$.active_model
$.analysis_as_of
$.rule_version
$.data_coverage.status
$.liquidity.next_dol.label
$.liquidity.next_dol.score
$.ssmt.available
$.ssmt.detected
$.ssmt.sync_status
$.confirmation.sweep
$.confirmation.displacement
$.confirmation.mss
$.confirmation.fvg
$.trade_idea.reason_code
$.trade_idea.blocking_conditions
$.gate_result.passed
$.gate_result.failed_reasons
$.warnings
```

Narrative tests should not require exact sentence matches. They should assert that narrative includes the selected DOL label and the reason code or missing confirmation.

## 21. Failure Modes And Required Behavior

| Failure | Required Behavior |
|---|---|
| XAGUSD missing | Mark SSMT unavailable and warn |
| XAGUSD stale | Mark sync status stale and avoid false SSMT |
| Duplicate webhook | Upsert safely |
| Invalid payload | Return validation error |
| Insufficient HTF candles | Return WAIT with reason |
| Timezone parse failure | Reject payload or require explicit timezone |
| HTF and M15 conflict | Return WAIT unless model explicitly supports counter-context |
| No MSS | Return WAIT if MSS is required |
| No DOL candidate | Return WAIT |
| Data too old | Return WAIT with stale data warning |
| H4 missing but H1 present | Run degraded mode, require WAIT unless high-confidence DOL and complete gate |
| DOL candidates tied opposite direction | WAIT with `DOL_AMBIGUOUS` |
| SSMT timestamp mismatch | `sync_status=timestamp_mismatch`, SSMT unavailable |
| Analysis time before latest candle close | Use last closed candle only |
| Current price outside active range | Recompute range; if no valid range, WAIT |
| Spread/session abnormality unavailable | Warn, but do not block MVP |
| Duplicate but different candle OHLC | Upsert and record source/update timestamp |

## 22. Development Milestones

### Milestone 1 - Data Layer

- SQLite database.
- Candle schema.
- Webhook ingestion.
- CSV import.
- Data freshness status.

### Milestone 2 - HTF Context Engine

- HTF candle loading.
- Swing detection.
- Dealing range.
- Premium, discount, equilibrium.
- HTF IRL/ERL map.

### Milestone 3 - M15 Execution Engine

- M15 sweep detection.
- SSMT detection.
- Displacement detection.
- MSS/CHOCH detection.
- FVG detection.

### Milestone 4 - DOL And Trade Idea Gate

- DOL candidate scoring.
- Active model classification.
- WAIT-first trade idea generation.
- Narrative reasoning.
- Reason code taxonomy.
- Gate result output.

### Milestone 5 - API And MCP

- FastAPI analysis endpoints.
- MCP tools.
- Shared output schema.

### Milestone 6 - Minimal Dashboard

- Data status.
- HTF context panel.
- DOL panel.
- M15 confirmation checklist.
- SSMT panel.
- Trade idea and narrative.

### Milestone 7 - Future Extensions

- M5 refinement.
- DXY confirmation.
- Order block quality scoring.
- Backtest and replay mode.
- Browser-based TradingView reader.
- Broker/API feed integration.

### Implementation Sequencing Gates

Implementation should proceed in this order:

1. Data contract + candle store + `analysis_as_of`.
2. HTF range/swing engine.
3. IRL/ERL map.
4. DOL scoring with golden fixtures.
5. M15 confirmation engine.
6. Trade gate matrix.
7. API/MCP shared schema.
8. Minimal dashboard.

Do not start frontend dashboard work before the shared analysis schema and at least four golden fixtures pass.

## 23. Prompt For Codex Implementation

```text
Build a full-stack MCP Trading Strategy Discipline Engine based on this PRD.

Project name: trading-strategy-mcp

Positioning:
This is not a signal bot. It is a WAIT-first ICT/SMC strategy debugger and discipline engine.

Core rule:
HTF context determines bias and DOL.
M15 determines whether execution is valid or WAIT.
WAIT is the default when context, data, or gate confirmations are incomplete.

Tech stack:
- Backend: Python 3.11, FastAPI, Pydantic, Pandas, NumPy
- Database: SQLite
- MCP: MCP Python SDK
- Frontend: React, Vite, Tailwind CSS
- Tests: Pytest

Build:
1. TradingView webhook candle ingestion.
2. CSV import fallback.
3. SQLite candle storage.
4. Reproducible `analysis_as_of` analysis.
5. HTF context engine for required H1 + H4, with D1 PDH/PDL when available.
6. Deterministic swing/range rules using the PRD parameters.
7. IRL/ERL liquidity map.
8. Deterministic DOL scoring formula and tie-breakers.
9. M15 execution engine.
10. SSMT XAUUSD/XAGUSD detection with sync states.
11. Sweep, displacement, MSS/CHOCH, and FVG detection.
12. WAIT-first trade gate matrix with reason codes and blocking conditions.
13. JSON analysis output and narrative report.
14. MCP tools: analyze_market, detect_liquidity, detect_ssmt, generate_trade_idea.
15. Minimal frontend dashboard.
16. Oracle-driven golden fixtures with manifest.json files.
17. README with backend, frontend, MCP, TradingView webhook, and CSV instructions.

Do not build auto trade execution.
Do not produce BUY/SELL unless required confirmations are complete.
If HTF context is unavailable or conflicting, action must be WAIT with a reason.
API and MCP must expose the same deterministic engine output.
Narrative text must only explain engine decisions, never create decisions.
```

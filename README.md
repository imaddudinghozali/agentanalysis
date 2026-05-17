# MCP Trading Strategy Discipline Engine

WAIT-first ICT/SMC strategy analysis for XAUUSD with XAGUSD SSMT context. The dashboard in this repo is intentionally thin: it displays deterministic engine output and does not implement trading logic.

## Backend

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Core endpoints:

- `POST /webhook/tradingview` ingests one TradingView candle and upserts by symbol, timeframe, and UTC time.
- `POST /api/import-csv` imports fixture or backfill candles from `csv_text`, `csv_path`, or multipart upload.
- `POST /api/analyze` returns deterministic HTF/M15 analysis for a required `analysis_as_of`.
- `POST /api/report` returns the same analysis as a dashboard/agent-friendly report payload.
- `GET /api/status` returns latest candle freshness, missing timeframes, and SSMT availability.

Example webhook payload:

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

Example CSV import:

```bash
curl -X POST http://127.0.0.1:8000/api/import-csv ^
  -H "Content-Type: application/json" ^
  -d "{\"symbol\":\"XAUUSD\",\"timeframe\":\"M15\",\"csv_path\":\"data/fixtures/xauusd_m15_sample.csv\"}"
```

Example analysis request:

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

The engine only uses candles closed at or before `analysis_as_of`, so fixture and replay analyses are reproducible.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL printed by the command, usually `http://127.0.0.1:5173`.

The dashboard starts with a local fixture analysis from `frontend/src/sampleAnalysis.js`. When the API is available, set the API field to the backend base URL and use refresh. The frontend posts this request to `/api/analyze`:

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

## MCP Server

MCP is an integration layer over the same `AnalysisService` used by the API. It does not implement separate trading logic.

Run the MCP server:

```bash
python server.py
```

Set a database path when you want MCP tools to read the same SQLite file as the API:

```bash
set TRADING_STRATEGY_DB_PATH=data/trading_strategy.sqlite3
python server.py
```

MCP tools:

- `analyze_market`
- `detect_liquidity`
- `detect_ssmt`
- `generate_trade_idea`

Tests assert that these tools return the same deterministic payloads as the API for the same request.

## Fixture Data

Sample CSV candles live in `data/fixtures/`:

- `xauusd_m15_sample.csv`
- `xagusd_m15_sample.csv`
- `xauusd_h1_sample.csv`
- `xauusd_h4_sample.csv`
- `xauusd_d1_sample.csv`

Each CSV uses:

```text
time,open,high,low,close,volume
```

All fixture timestamps are UTC.

## Golden Manifests

Oracle-driven manifest examples live under `tests/fixtures/**/manifest.json`. Each manifest declares:

- fixture id
- symbols and timeframes
- source CSV files or webhook payloads
- `analysis_as_of`
- expected action, bias, model, DOL, reason code, warnings
- required confirmations
- JSON paths that tests should assert

The manifests cover the PRD's required MVP cases, including complete BUY/SELL gates, WAIT reason codes, SSMT unavailable/stale states, insufficient HTF data, and duplicate webhook upsert behavior.

## Tests

Use the local dependency path in this workspace when the global/user Python site-packages are not visible:

```bash
$env:PYTHONPATH=".deps"; python -m pytest -q
```

Expected current result: all tests pass.

Frontend build:

```bash
cd frontend
npm.cmd run build
```

## PRD Coverage Notes

Implemented MVP coverage includes:

- WAIT-first trade gate with explicit reason codes and blocking conditions.
- HTF context from H1/H4 with D1 PDH/PDL candidates when available.
- H1-only degraded mode when H4 is missing and H1/M15 are complete.
- DOL candidate scoring with liquidity type, HTF location, range alignment, execution evidence, session, and proximity penalty.
- SSMT states for aligned, missing, stale, timestamp mismatch, and insufficient data.
- Golden fixtures for BUY/SELL complete gates, WAIT reasons, stale/missing data, HTF/M15 conflict, ambiguous/no DOL, and duplicate webhook upsert.
- PRD acceptance guards for reason-code taxonomy, strategy defaults, persistence tables, dashboard analysis request, and 20 labeled DOL-direction setup examples.

Out of MVP scope per the PRD: trade execution, broker integration, full backtesting, machine learning, DXY confirmation, M5 refinement, and TradingView browser automation.

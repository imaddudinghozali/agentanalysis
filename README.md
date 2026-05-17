# MCP Trading Strategy Discipline Engine

WAIT-first ICT/SMC strategy analysis for XAUUSD with XAGUSD SSMT context. The dashboard in this repo is intentionally thin: it displays deterministic engine output and does not implement trading logic.

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

## Backend And MCP

Backend/API ownership is separate from this frontend fixture pass. The PRD expects:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Expected endpoints:

- `POST /webhook/tradingview` for one candle upsert.
- `POST /api/import-csv` for CSV import.
- `POST /api/analyze` for deterministic analysis output.
- `GET /api/status` for candle freshness and missing timeframe warnings.

Expected MCP tools:

- `analyze_market`
- `detect_liquidity`
- `detect_ssmt`
- `generate_trade_idea`

MCP tools should call the same shared analysis service as the API.

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

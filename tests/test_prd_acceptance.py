from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app import create_app
from schemas.trade import ReasonCode
from strategy.common import StrategyConfig
from strategy.config import DEFAULT_PARAMS


FIXTURE_ROOT = Path(__file__).parent / "fixtures"
LABELED_SETUP_PATH = FIXTURE_ROOT / "labeled_setup_examples.json"

PRD_REASON_CODES = {
    "MISSING_HTF_CONTEXT",
    "NO_ACTIVE_DEALING_RANGE",
    "UNCLEAR_DOL",
    "DOL_AMBIGUOUS",
    "HTF_CONFLICT",
    "HTF_M15_CONFLICT",
    "MISSING_SWEEP",
    "MISSING_SSMT",
    "SSMT_UNAVAILABLE",
    "MISSING_DISPLACEMENT",
    "MISSING_MSS",
    "MISSING_FVG",
    "MISSING_INVALIDATION",
    "STALE_DATA",
    "INSUFFICIENT_DATA",
    "GATE_COMPLETE",
}


def _manifest(fixture_id: str) -> dict:
    return json.loads((FIXTURE_ROOT / fixture_id / "manifest.json").read_text(encoding="utf-8"))


def _import_manifest_csvs(client: TestClient, manifest: dict, manifest_path: Path) -> None:
    for key, relative_csv_path in manifest.get("csv_files", {}).items():
        symbol, timeframe = key.split("_", 1)
        csv_text = (manifest_path.parent / relative_csv_path).resolve().read_text(encoding="utf-8")
        response = client.post(
            "/api/import-csv",
            json={"symbol": symbol, "timeframe": timeframe, "csv_text": csv_text},
        )
        assert response.status_code == 200


def _analyze_fixture(tmp_path: Path, fixture_id: str) -> dict:
    manifest_path = FIXTURE_ROOT / fixture_id / "manifest.json"
    manifest = _manifest(fixture_id)
    client = TestClient(create_app(tmp_path / f"{fixture_id}.sqlite3"))
    _import_manifest_csvs(client, manifest, manifest_path)
    response = client.post(
        "/api/analyze",
        json={
            "primary_symbol": "XAUUSD",
            "secondary_symbol": "XAGUSD",
            "execution_timeframe": "M15",
            "context_timeframes": ["H4", "H1", "D1"],
            "analysis_as_of": manifest["analysis_as_of"],
            "mode": "normal",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_prd_reason_code_taxonomy_is_complete():
    assert {reason.value for reason in ReasonCode} == PRD_REASON_CODES


def test_strategy_defaults_match_prd_detection_parameters():
    config = StrategyConfig()
    for name, value in DEFAULT_PARAMS.items():
        assert getattr(config, name) == value
    assert config.minimum_m15_candles == 200


def test_prd_database_tables_are_initialized(tmp_path):
    db_path = tmp_path / "schema.sqlite3"
    TestClient(create_app(db_path))
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {"candles", "analysis_history", "rule_runs", "uploaded_files"} <= tables


def test_dashboard_refresh_request_tracks_primary_fixture_time():
    source = Path("frontend/src/sampleAnalysis.js").read_text(encoding="utf-8")
    assert 'analysis_as_of: "2026-05-16T13:30:00Z"' in source


def test_labeled_setup_examples_meet_prd_dol_direction_threshold(tmp_path):
    cases = json.loads(LABELED_SETUP_PATH.read_text(encoding="utf-8"))
    assert len(cases) == 20

    fixture_results: dict[str, dict] = {}
    for fixture_id in sorted({case["fixture_id"] for case in cases}):
        fixture_results[fixture_id] = _analyze_fixture(tmp_path, fixture_id)

    matches = 0
    for case in cases:
        result = fixture_results[case["fixture_id"]]
        engine_direction = result["liquidity"]["next_dol"].get("direction")
        if engine_direction == case["trader_dol_direction"]:
            matches += 1

    assert matches / len(cases) >= 0.70

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import create_app


FIXTURE_ROOT = Path(__file__).parent / "fixtures"
EXPECTED_FIXTURES = {
    "bearish_complete_model_001",
    "bullish_complete_model_001",
    "bearish_missing_mss_001",
    "bullish_missing_displacement_001",
    "htf_bullish_m15_bearish_conflict_001",
    "equilibrium_unclear_dol_001",
    "missing_xagusd_required_ssmt_001",
    "secondary_stale_001",
    "insufficient_htf_001",
    "duplicate_webhook_001",
}
REQUIRED_MANIFEST_KEYS = {
    "fixture_id",
    "symbols",
    "timeframes",
    "analysis_as_of",
    "expected_action",
    "expected_bias",
    "expected_active_model",
    "expected_dol_label",
    "expected_reason_code",
    "required_confirmations",
    "expected_warnings",
    "json_assertions",
}


def _manifest_paths() -> list[Path]:
    return sorted(FIXTURE_ROOT.glob("*/manifest.json"))


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _import_manifest_csvs(client: TestClient, manifest_path: Path, manifest: dict) -> None:
    for key, relative_csv_path in manifest.get("csv_files", {}).items():
        symbol, timeframe = key.split("_", 1)
        csv_text = (manifest_path.parent / relative_csv_path).resolve().read_text(encoding="utf-8")
        response = client.post(
            "/api/import-csv",
            json={"symbol": symbol, "timeframe": timeframe, "csv_text": csv_text},
        )
        assert response.status_code == 200
        assert response.json()["rows_imported"] > 0


def test_prd_golden_fixture_inventory_is_complete():
    actual = {path.parent.name for path in _manifest_paths()}
    assert actual == EXPECTED_FIXTURES


def test_golden_fixture_manifests_are_oracle_driven():
    for path in _manifest_paths():
        manifest = _load_manifest(path)
        assert set(manifest) >= REQUIRED_MANIFEST_KEYS
        assert manifest["fixture_id"] == path.parent.name
        assert isinstance(manifest["symbols"], list)
        assert isinstance(manifest["timeframes"], list)
        assert isinstance(manifest["required_confirmations"], dict)
        assert isinstance(manifest["expected_warnings"], list)
        assert isinstance(manifest["json_assertions"], list)
        assert manifest["json_assertions"]

        for relative_csv_path in manifest.get("csv_files", {}).values():
            csv_path = (path.parent / relative_csv_path).resolve()
            assert csv_path.exists(), f"{manifest['fixture_id']} references missing CSV {csv_path}"


def test_duplicate_webhook_manifest_executes_storage_oracle(tmp_path):
    manifest = _load_manifest(FIXTURE_ROOT / "duplicate_webhook_001" / "manifest.json")
    client = TestClient(create_app(tmp_path / "fixture.sqlite3"))

    responses = [
        client.post("/webhook/tradingview", json=payload)
        for payload in manifest["webhook_payloads"]
    ]
    assert all(response.status_code == 200 for response in responses)

    status = client.get("/api/status")
    assert status.status_code == 200
    candle_rows = [
        row
        for row in status.json()["last_candles"]
        if row["symbol"] == "XAUUSD" and row["timeframe"] == "M15"
    ]
    assert len(candle_rows) == 1
    assert candle_rows[0]["candle_count"] == manifest["expected_storage"]["expected_rows_after_duplicate_upsert"]


def test_analysis_manifests_execute_expected_oracles(tmp_path):
    for manifest_path in _manifest_paths():
        manifest = _load_manifest(manifest_path)
        if "webhook_payloads" in manifest:
            continue
        client = TestClient(create_app(tmp_path / f"{manifest['fixture_id']}.sqlite3"))
        _import_manifest_csvs(client, manifest_path, manifest)

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
        body = response.json()
        next_dol = body.get("liquidity", {}).get("next_dol") or {}
        assert body["action"] == manifest["expected_action"], manifest["fixture_id"]
        assert body["bias"] == manifest["expected_bias"], manifest["fixture_id"]
        assert body["active_model"] == manifest["expected_active_model"], manifest["fixture_id"]
        assert next_dol.get("label") == manifest["expected_dol_label"], manifest["fixture_id"]
        assert body["trade_idea"]["reason_code"] == manifest["expected_reason_code"], manifest["fixture_id"]
        for warning in manifest["expected_warnings"]:
            assert warning in body["warnings"], manifest["fixture_id"]

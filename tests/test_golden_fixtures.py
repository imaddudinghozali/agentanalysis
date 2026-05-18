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
PRD_REQUIRED_JSON_PATHS = {
    "$.action",
    "$.bias",
    "$.active_model",
    "$.analysis_as_of",
    "$.rule_version",
    "$.data_coverage.status",
    "$.liquidity.next_dol.label",
    "$.liquidity.next_dol.score",
    "$.ssmt.available",
    "$.ssmt.detected",
    "$.ssmt.sync_status",
    "$.confirmation.sweep",
    "$.confirmation.displacement",
    "$.confirmation.mss",
    "$.confirmation.fvg",
    "$.trade_idea.reason_code",
    "$.trade_idea.blocking_conditions",
    "$.gate_result.passed",
    "$.gate_result.failed_reasons",
    "$.warnings",
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


def _analyze_fixture(client: TestClient, manifest: dict) -> dict:
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


def _json_path_value(body: dict, path: str):
    assert path.startswith("$.")
    value = body
    for part in path[2:].split("."):
        assert isinstance(value, dict), path
        assert part in value, path
        value = value[part]
    return value


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
        if "webhook_payloads" not in manifest:
            assert PRD_REQUIRED_JSON_PATHS <= set(manifest["json_assertions"])

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

        body = _analyze_fixture(client, manifest)
        rerun_body = _analyze_fixture(client, manifest)
        assert rerun_body == body, manifest["fixture_id"]
        next_dol = body.get("liquidity", {}).get("next_dol") or {}
        assert body["data_coverage"]["counts"], manifest["fixture_id"]
        assert body["data_coverage"]["last_candles"], manifest["fixture_id"]
        assert "current_price" in body["htf_context"], manifest["fixture_id"]
        assert "bias_source" in body["htf_context"], manifest["fixture_id"]
        assert body["action"] == manifest["expected_action"], manifest["fixture_id"]
        assert body["bias"] == manifest["expected_bias"], manifest["fixture_id"]
        assert body["active_model"] == manifest["expected_active_model"], manifest["fixture_id"]
        assert next_dol.get("label") == manifest["expected_dol_label"], manifest["fixture_id"]
        assert body["trade_idea"]["reason_code"] == manifest["expected_reason_code"], manifest["fixture_id"]
        required_confirmations = manifest["required_confirmations"]
        if "bullish_ssmt" in required_confirmations:
            assert body["ssmt"]["detected"] is required_confirmations["bullish_ssmt"], manifest["fixture_id"]
            if required_confirmations["bullish_ssmt"]:
                assert body["ssmt"]["type"] == "bullish", manifest["fixture_id"]
        if "bearish_ssmt" in required_confirmations:
            assert body["ssmt"]["detected"] is required_confirmations["bearish_ssmt"], manifest["fixture_id"]
            if required_confirmations["bearish_ssmt"]:
                assert body["ssmt"]["type"] == "bearish", manifest["fixture_id"]
        for path in PRD_REQUIRED_JSON_PATHS:
            _json_path_value(body, path)
        if body["action"] in {"BUY", "SELL"}:
            assert body["gate_result"]["passed"] is True, manifest["fixture_id"]
            assert body["trade_idea"]["reason_code"] == "GATE_COMPLETE", manifest["fixture_id"]
            assert set(body["gate_result"]["required_confirmations"]) <= set(
                body["gate_result"]["present_confirmations"]
            ), manifest["fixture_id"]
        else:
            assert body["gate_result"]["passed"] is False, manifest["fixture_id"]
        narrative = body.get("narrative_report") or body.get("narrative", "")
        assert next_dol.get("label") in narrative, manifest["fixture_id"]
        assert body["trade_idea"]["reason_code"] in narrative, manifest["fixture_id"]
        for warning in manifest["expected_warnings"]:
            assert warning in body["warnings"], manifest["fixture_id"]

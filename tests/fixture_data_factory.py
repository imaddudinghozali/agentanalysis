from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from strategy import analyze_market
from tests.test_strategy_engine import candle, make_conflicting_h1, market


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "fixtures" / "generated"
MANIFEST_ROOT = ROOT / "tests" / "fixtures"


def _mirror_row(row: dict) -> dict:
    def mirror_price(value: float) -> float:
        return 200 - float(value)

    return {
        "time": row["time"],
        "open": mirror_price(row["open"]),
        "high": mirror_price(row["low"]),
        "low": mirror_price(row["high"]),
        "close": mirror_price(row["close"]),
        "volume": row.get("volume", 1),
    }


def _mirror(data: dict) -> dict:
    return {
        "XAUUSD": {timeframe: [_mirror_row(row) for row in rows] for timeframe, rows in data["XAUUSD"].items()},
        "XAGUSD": {"M15": [_mirror_row(row) for row in data.get("XAGUSD", {}).get("M15", [])]},
    }


def _set_row(rows: list[dict], index: int, values: tuple[float, float, float, float]) -> None:
    rows[index] = candle(datetime.fromisoformat(rows[index]["time"].replace("Z", "+00:00")), *values)


def _missing_displacement_bearish() -> dict:
    data = market(with_mss=True)
    rows = data["XAUUSD"]["M15"]
    overrides = {
        205: (107, 109, 106.8, 107.5),
        206: (107.5, 107.8, 102, 107.2),
        207: (97.2, 101.2, 96.8, 97.0),
        208: (93.2, 96, 92, 93.0),
        209: (93.0, 96, 92, 93.1),
    }
    for index, values in overrides.items():
        _set_row(rows, index, values)
    data["XAGUSD"]["M15"] = _secondary_from_primary(rows)
    return data


def _secondary_from_primary(primary: list[dict]) -> list[dict]:
    return [{**row, "high": min(row["high"], 104), "low": row["low"] + 0.2, "close": row["close"]} for row in primary]


def _htf_m15_conflict() -> dict:
    bearish = market(with_mss=True)
    bullish_htf = _mirror(market(with_mss=True))
    bullish_htf["XAUUSD"]["M15"] = bearish["XAUUSD"]["M15"]
    bullish_htf["XAGUSD"]["M15"] = bearish["XAGUSD"]["M15"]
    return bullish_htf


def _equilibrium_unclear_dol() -> dict:
    data = market(with_mss=True)
    rows = data["XAUUSD"]["M15"]
    _set_row(rows, -1, (90, 91, 89, 90))
    data["XAGUSD"]["M15"] = _secondary_from_primary(rows)
    return data


def _insufficient_htf() -> dict:
    data = market(with_mss=True)
    return {
        "XAUUSD": {"M15": data["XAUUSD"]["M15"]},
        "XAGUSD": {"M15": data["XAGUSD"]["M15"]},
    }


def _missing_secondary() -> dict:
    data = market(with_mss=True)
    return {"XAUUSD": data["XAUUSD"], "XAGUSD": {}}


def _secondary_stale() -> dict:
    data = market(with_mss=True)
    data["XAGUSD"]["M15"] = [{**row, "time": "2026-05-01T00:00:00Z"} for row in data["XAGUSD"]["M15"]]
    return data


SCENARIOS: dict[str, Callable[[], dict]] = {
    "bearish_complete_model_001": lambda: market(with_mss=True),
    "bearish_missing_mss_001": lambda: market(with_mss=False),
    "bullish_complete_model_001": lambda: _mirror(market(with_mss=True)),
    "bullish_missing_displacement_001": lambda: _mirror(_missing_displacement_bearish()),
    "htf_bullish_m15_bearish_conflict_001": _htf_m15_conflict,
    "equilibrium_unclear_dol_001": _equilibrium_unclear_dol,
    "missing_xagusd_required_ssmt_001": _missing_secondary,
    "secondary_stale_001": _secondary_stale,
    "insufficient_htf_001": _insufficient_htf,
}


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "time": row["time"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row.get("volume", 1),
                }
            )


def _csv_files_for(fixture_id: str, data: dict) -> dict[str, str]:
    csv_files: dict[str, str] = {}
    fixture_dir = DATA_ROOT / fixture_id
    for symbol, by_timeframe in data.items():
        for timeframe, rows in by_timeframe.items():
            if not rows:
                continue
            filename = f"{symbol.lower()}_{timeframe.lower()}.csv"
            _write_csv(fixture_dir / filename, rows)
            csv_files[f"{symbol}_{timeframe}"] = f"../../../data/fixtures/generated/{fixture_id}/{filename}"
    return csv_files


def _update_manifest(fixture_id: str, data: dict, csv_files: dict[str, str]) -> None:
    manifest_path = MANIFEST_ROOT / fixture_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    as_of = data["XAUUSD"]["M15"][-1]["time"]
    result = analyze_market(data, analysis_as_of=as_of)
    dol = result.get("liquidity", {}).get("next_dol") or {}
    manifest["analysis_as_of"] = as_of
    manifest["csv_files"] = csv_files
    manifest["expected_action"] = result.get("action")
    manifest["expected_bias"] = result.get("bias")
    manifest["expected_active_model"] = result.get("active_model")
    manifest["expected_dol_label"] = dol.get("label")
    manifest["expected_reason_code"] = result.get("trade_idea", {}).get("reason_code")
    manifest["expected_warnings"] = result.get("warnings", [])
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def write_generated_fixtures() -> None:
    for fixture_id, factory in SCENARIOS.items():
        data = factory()
        csv_files = _csv_files_for(fixture_id, data)
        _update_manifest(fixture_id, data, csv_files)


if __name__ == "__main__":
    write_generated_fixtures()

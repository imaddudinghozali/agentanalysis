from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from schemas.candle import CandlePayload
from storage.database import connect, init_db


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_db_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class CandleRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = db_path
        init_db(db_path)

    def upsert_candle(self, candle: CandlePayload, source: str = "webhook") -> dict[str, Any]:
        time_utc = iso_utc(candle.time)
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO candles (
                    symbol, timeframe, time_utc, open, high, low, close, volume, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe, time_utc) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    source = excluded.source,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    candle.symbol,
                    candle.timeframe,
                    time_utc,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                    source,
                ),
            )
        return {
            "status": "upserted",
            "symbol": candle.symbol,
            "timeframe": candle.timeframe,
            "time_utc": parse_db_time(time_utc),
            "source": source,
        }

    def bulk_upsert(self, candles: list[CandlePayload], source: str = "csv") -> int:
        if not candles:
            return 0
        rows = [
            (
                candle.symbol,
                candle.timeframe,
                iso_utc(candle.time),
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                source,
            )
            for candle in candles
        ]
        with connect(self.db_path) as connection:
            connection.executemany(
                """
                INSERT INTO candles (
                    symbol, timeframe, time_utc, open, high, low, close, volume, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe, time_utc) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    source = excluded.source,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
        return len(rows)

    def list_candles(
        self,
        symbol: str,
        timeframe: str,
        as_of: datetime | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT symbol, timeframe, time_utc, open, high, low, close, volume, source
            FROM candles
            WHERE symbol = ? AND timeframe = ?
        """
        params: list[Any] = [symbol.upper(), timeframe.upper()]
        if as_of is not None:
            query += " AND time_utc <= ?"
            params.append(iso_utc(as_of))
        query += " ORDER BY time_utc ASC"
        if limit is not None:
            query = f"SELECT * FROM ({query}) ORDER BY time_utc DESC LIMIT ?"
            params.append(limit)
        with connect(self.db_path) as connection:
            rows = [dict(row) for row in connection.execute(query, params).fetchall()]
        rows = list(reversed(rows)) if limit is not None else rows
        for row in rows:
            row["time_utc"] = parse_db_time(row["time_utc"])
        return rows

    def latest_by_symbol_timeframe(self) -> list[dict[str, Any]]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT c.symbol, c.timeframe, c.time_utc, c.close, c.source, counts.candle_count
                FROM candles c
                JOIN (
                    SELECT symbol, timeframe, MAX(time_utc) AS max_time, COUNT(*) AS candle_count
                    FROM candles
                    GROUP BY symbol, timeframe
                ) counts
                  ON counts.symbol = c.symbol
                 AND counts.timeframe = c.timeframe
                 AND counts.max_time = c.time_utc
                ORDER BY c.symbol, c.timeframe
                """
            ).fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["time_utc"] = parse_db_time(row["time_utc"])
        return result

    def count_candles(self, symbol: str, timeframe: str, as_of: datetime | None = None) -> int:
        query = "SELECT COUNT(*) FROM candles WHERE symbol = ? AND timeframe = ?"
        params: list[Any] = [symbol.upper(), timeframe.upper()]
        if as_of is not None:
            query += " AND time_utc <= ?"
            params.append(iso_utc(as_of))
        with connect(self.db_path) as connection:
            return int(connection.execute(query, params).fetchone()[0])

    def record_uploaded_file(self, symbol: str, timeframe: str, file_path: str, rows_imported: int) -> None:
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO uploaded_files (symbol, timeframe, file_path, rows_imported)
                VALUES (?, ?, ?, ?)
                """,
                (symbol.upper(), timeframe.upper(), file_path, rows_imported),
            )

    def record_analysis(self, result: dict[str, Any]) -> int:
        selected_dol = result.get("liquidity", {}).get("next_dol") or {}
        trade_idea = result.get("trade_idea") or {}
        gate_result = result.get("gate_result") or {}
        data_coverage = result.get("data_coverage") or {}
        with connect(self.db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO analysis_history (
                    primary_symbol, secondary_symbol, execution_timeframe, context_timeframes,
                    analysis_as_of, rule_version, active_model, bias, action, dol_label,
                    confidence, data_coverage_json, gate_result_json, result_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.get("primary_symbol"),
                    result.get("secondary_symbol"),
                    result.get("execution_timeframe"),
                    json.dumps(result.get("context_timeframes", [])),
                    result.get("analysis_as_of"),
                    result.get("rule_version"),
                    result.get("active_model"),
                    result.get("bias"),
                    trade_idea.get("action") or result.get("action"),
                    selected_dol.get("label"),
                    result.get("confidence"),
                    json.dumps(data_coverage, sort_keys=True),
                    json.dumps(gate_result, sort_keys=True),
                    json.dumps(result, sort_keys=True, default=str),
                ),
            )
            analysis_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO rule_runs (
                    analysis_id, rule_version, selected_dol_score, active_model,
                    gate_passed, failed_reasons
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    result.get("rule_version"),
                    selected_dol.get("score"),
                    result.get("active_model"),
                    bool(gate_result.get("passed", False)),
                    json.dumps(gate_result.get("failed_reasons", [])),
                ),
            )
        return analysis_id

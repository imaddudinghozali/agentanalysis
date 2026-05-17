from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError

from schemas.candle import CandlePayload, CSVImportResult
from storage.candles import CandleRepository


REQUIRED_CSV_COLUMNS = {"time", "open", "high", "low", "close", "volume"}


class IngestionService:
    def __init__(self, repository: CandleRepository) -> None:
        self.repository = repository

    def ingest_candle(self, payload: CandlePayload, source: str = "webhook") -> dict:
        return self.repository.upsert_candle(payload, source=source)

    def import_csv_file(self, symbol: str, timeframe: str, file_path: str | Path) -> CSVImportResult:
        path = Path(file_path)
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            result = self.import_csv_stream(symbol, timeframe, handle, source=str(path))
        self.repository.record_uploaded_file(symbol, timeframe, str(path), result.rows_imported)
        return result

    def import_csv_text(self, symbol: str, timeframe: str, csv_text: str, source: str = "inline_csv") -> CSVImportResult:
        result = self.import_csv_stream(symbol, timeframe, io.StringIO(csv_text), source=source)
        self.repository.record_uploaded_file(symbol, timeframe, source, result.rows_imported)
        return result

    def import_csv_stream(self, symbol: str, timeframe: str, stream: TextIO, source: str) -> CSVImportResult:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or [])
        missing_columns = sorted(REQUIRED_CSV_COLUMNS - columns)
        if missing_columns:
            return CSVImportResult(
                status="imported",
                symbol=symbol.upper(),
                timeframe=timeframe.upper(),
                rows_imported=0,
                rows_rejected=0,
                source=source,
                errors=[f"missing required column(s): {', '.join(missing_columns)}"],
            )

        candles: list[CandlePayload] = []
        errors: list[str] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                candle = CandlePayload(
                    symbol=symbol,
                    timeframe=timeframe,
                    time=datetime.fromisoformat(row["time"].replace("Z", "+00:00")),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]) if row.get("volume") not in (None, "") else None,
                )
                candles.append(candle)
            except (ValueError, ValidationError) as exc:
                errors.append(f"line {line_number}: {exc}")

        imported = self.repository.bulk_upsert(candles, source="csv")
        return CSVImportResult(
            status="imported",
            symbol=symbol.upper(),
            timeframe=timeframe.upper(),
            rows_imported=imported,
            rows_rejected=len(errors),
            source=source,
            errors=errors,
        )

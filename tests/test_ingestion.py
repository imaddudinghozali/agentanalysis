from __future__ import annotations

from services.ingestion_service import IngestionService
from storage.candles import CandleRepository


def test_csv_validation_reports_missing_columns(tmp_path):
    service = IngestionService(CandleRepository(tmp_path / "test.sqlite3"))

    result = service.import_csv_text(
        "XAUUSD",
        "M15",
        "time,open,high,low,close\n2026-05-16T12:00:00Z,1,2,0.5,1.5\n",
    )

    assert result.rows_imported == 0
    assert result.errors == ["missing required column(s): volume"]

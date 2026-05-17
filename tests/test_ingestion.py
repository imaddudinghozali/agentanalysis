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


def test_csv_import_rejects_invalid_ohlc_rows_without_importing_them(tmp_path):
    service = IngestionService(CandleRepository(tmp_path / "test.sqlite3"))

    result = service.import_csv_text(
        "XAUUSD",
        "M15",
        "\n".join(
            [
                "time,open,high,low,close,volume",
                "2026-05-16T12:00:00Z,100,101,99,100.5,10",
                "2026-05-16T12:15:00Z,100,99,98,100.5,10",
            ]
        ),
    )

    assert result.rows_imported == 1
    assert result.rows_rejected == 1
    assert "high must be greater than or equal" in result.errors[0]

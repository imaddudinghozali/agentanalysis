from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError
from starlette.middleware.cors import CORSMiddleware
from starlette.datastructures import UploadFile

from schemas.candle import CandlePayload
from schemas.market import AnalysisRequest
from services.analysis_service import AnalysisService
from services.ingestion_service import IngestionService
from services.tradingview_service import TradingViewFetchError, TradingViewMarketDataService
from storage.candles import CandleRepository
from storage.database import init_db


def create_app(db_path: str | Path | None = None) -> FastAPI:
    repository = CandleRepository(db_path)
    ingestion_service = IngestionService(repository)
    analysis_service = AnalysisService(repository)
    tradingview_service = TradingViewMarketDataService(repository)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(db_path)
        yield

    app = FastAPI(
        title="MCP Trading Strategy Discipline Engine API",
        version="0.1.0",
        description="WAIT-first API for candle ingestion, market analysis, and data status.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:4173",
            "http://localhost:4173",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):(41|51)\d{2}$",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhook/tradingview")
    def tradingview_webhook(payload: CandlePayload) -> dict[str, Any]:
        return ingestion_service.ingest_candle(payload, source="webhook")

    @app.post("/api/import-csv")
    async def import_csv(request: Request) -> dict[str, Any]:
        content_type = request.headers.get("content-type", "")
        try:
            if content_type.startswith("multipart/form-data"):
                form = await request.form()
                symbol = str(form.get("symbol") or "")
                timeframe = str(form.get("timeframe") or "")
                upload = form.get("file")
                csv_path = form.get("csv_path")
                if isinstance(upload, UploadFile):
                    raw = await upload.read()
                    result = ingestion_service.import_csv_text(
                        symbol,
                        timeframe,
                        raw.decode("utf-8-sig"),
                        source=upload.filename or "upload.csv",
                    )
                elif csv_path:
                    result = ingestion_service.import_csv_file(symbol, timeframe, str(csv_path))
                else:
                    raise HTTPException(status_code=400, detail="file or csv_path is required")
            else:
                body = await request.json()
                symbol = body.get("symbol", "")
                timeframe = body.get("timeframe", "")
                if body.get("csv_text") is not None:
                    result = ingestion_service.import_csv_text(
                        symbol,
                        timeframe,
                        body["csv_text"],
                        source=body.get("source", "inline_csv"),
                    )
                elif body.get("csv_path") is not None:
                    result = ingestion_service.import_csv_file(symbol, timeframe, body["csv_path"])
                else:
                    raise HTTPException(status_code=400, detail="csv_text or csv_path is required")
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        if result.errors and result.rows_imported == 0:
            raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
        return result.model_dump(mode="json")

    @app.post("/api/analyze")
    def analyze(request: AnalysisRequest) -> dict[str, Any]:
        return analysis_service.analyze(request)

    @app.post("/api/report")
    def report(request: AnalysisRequest) -> dict[str, Any]:
        return analysis_service.report(request)

    @app.post("/api/tradingview/analyze")
    async def tradingview_analyze() -> dict[str, Any]:
        try:
            return await app.state.tradingview_service.refresh_and_analyze(analysis_service)
        except TradingViewFetchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return analysis_service.status()

    app.state.repository = repository
    app.state.ingestion_service = ingestion_service
    app.state.analysis_service = analysis_service
    app.state.tradingview_service = tradingview_service
    return app


app = create_app()

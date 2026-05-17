from __future__ import annotations

import importlib
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from schemas.market import AnalysisRequest
from schemas.trade import Action, ReasonCode
from services.report_service import build_narrative, build_report_payload
from storage.candles import CandleRepository, iso_utc


RULE_VERSION = "mvp-0.1"
MINIMUMS = {"M15": 200, "H1": 120, "H4": 80, "D1": 30}
SSMT_ALIGNMENT_TOLERANCE_SECONDS = 60
SECONDARY_STALE_AFTER_SECONDS = 15 * 60


class AnalysisService:
    def __init__(self, repository: CandleRepository) -> None:
        self.repository = repository

    def analyze(self, request: AnalysisRequest | dict[str, Any], persist: bool = True) -> dict[str, Any]:
        if isinstance(request, dict):
            request = AnalysisRequest(**request)
        market_data = self._load_market_data(request)
        result = self._run_strategy_pipeline_if_available(request, market_data)
        if result is None:
            result = self._fallback_analysis(request, market_data)
        result = self._normalize_analysis_result(request, result, market_data)
        if persist:
            self.repository.record_analysis(result)
        return result

    def detect_liquidity(self, request: AnalysisRequest | dict[str, Any]) -> dict[str, Any]:
        result = self.analyze(request, persist=False)
        return {
            "liquidity": result.get("liquidity", {}),
            "dol_candidates": result.get("dol_candidates", []),
            "htf_context": result.get("htf_context", {}),
            "warnings": result.get("warnings", []),
        }

    def detect_ssmt(self, request: AnalysisRequest | dict[str, Any]) -> dict[str, Any]:
        result = self.analyze(request, persist=False)
        return {
            "ssmt": result.get("ssmt", {}),
            "warnings": [warning for warning in result.get("warnings", []) if "SSMT" in warning or "SECONDARY" in warning],
        }

    def generate_trade_idea(self, request: AnalysisRequest | dict[str, Any]) -> dict[str, Any]:
        result = self.analyze(request, persist=False)
        return {
            "trade_idea": result.get("trade_idea", {}),
            "gate_result": result.get("gate_result", {}),
            "narrative_report": result.get("narrative_report", build_narrative(result)),
        }

    def report(self, request: AnalysisRequest | dict[str, Any], persist: bool = True) -> dict[str, Any]:
        result = self.analyze(request, persist=persist)
        return build_report_payload(result)

    def status(self, now: datetime | None = None) -> dict[str, Any]:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        latest = self.repository.latest_by_symbol_timeframe()
        records = []
        for item in latest:
            age_seconds = int((now - item["time_utc"]).total_seconds())
            records.append(
                {
                    "symbol": item["symbol"],
                    "timeframe": item["timeframe"],
                    "last_candle_time": iso_utc(item["time_utc"]),
                    "last_close": item["close"],
                    "source": item["source"],
                    "candle_count": item["candle_count"],
                    "age_seconds": age_seconds,
                    "fresh": age_seconds <= self._freshness_threshold(item["timeframe"]),
                }
            )
        available = {(record["symbol"], record["timeframe"]) for record in records}
        missing = []
        for timeframe in ("M15", "H1", "H4"):
            if ("XAUUSD", timeframe) not in available:
                missing.append({"symbol": "XAUUSD", "timeframe": timeframe, "warning": "MISSING_TIMEFRAME"})
        ssmt_available = ("XAUUSD", "M15") in available and ("XAGUSD", "M15") in available
        return {
            "status": "ok",
            "last_candles": records,
            "missing_timeframes": missing,
            "ssmt": {
                "available": ssmt_available,
                "warning": None if ssmt_available else "SSMT_UNAVAILABLE",
            },
        }

    def _load_market_data(self, request: AnalysisRequest) -> dict[str, Any]:
        data: dict[str, Any] = {
            "primary": {},
            "secondary": {},
            "counts": {},
        }
        timeframes = sorted(set([request.execution_timeframe, *request.context_timeframes]))
        for timeframe in timeframes:
            candles = self.repository.list_candles(request.primary_symbol, timeframe, as_of=request.analysis_as_of)
            data["primary"][timeframe] = candles
            data["counts"][(request.primary_symbol, timeframe)] = len(candles)
        if request.secondary_symbol:
            candles = self.repository.list_candles(
                request.secondary_symbol, request.execution_timeframe, as_of=request.analysis_as_of
            )
            data["secondary"][request.execution_timeframe] = candles
            data["counts"][(request.secondary_symbol, request.execution_timeframe)] = len(candles)
        return data

    def _run_strategy_pipeline_if_available(self, request: AnalysisRequest, market_data: dict[str, Any]) -> dict[str, Any] | None:
        try:
            pipeline = importlib.import_module("strategy.pipeline")
        except ImportError:
            return None
        function = getattr(pipeline, "analyze_market", None)
        if function is not None:
            result = function(
                {
                    request.primary_symbol: market_data["primary"],
                    request.secondary_symbol: market_data["secondary"] if request.secondary_symbol else {},
                },
                primary_symbol=request.primary_symbol,
                secondary_symbol=request.secondary_symbol or "XAGUSD",
                execution_timeframe=request.execution_timeframe,
                context_timeframes=request.context_timeframes,
                analysis_as_of=request.analysis_as_of,
                mode=request.mode,
            )
            if isinstance(result, dict):
                return result
        return None

    def _normalize_analysis_result(self, request: AnalysisRequest, result: dict[str, Any], market_data: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(result)
        normalized.setdefault("primary_symbol", request.primary_symbol)
        normalized.setdefault("secondary_symbol", request.secondary_symbol)
        normalized.setdefault("execution_timeframe", request.execution_timeframe)
        normalized.setdefault("context_timeframes", request.context_timeframes)
        normalized.setdefault("analysis_as_of", iso_utc(request.analysis_as_of))
        normalized.setdefault("rule_version", RULE_VERSION)
        normalized.setdefault("warnings", [])
        normalized["warnings"] = self._dedupe(
            [*normalized.get("warnings", []), *self._stale_data_warnings(request, market_data)]
        )
        if "narrative_report" not in normalized:
            normalized["narrative_report"] = normalized.get("narrative") or build_narrative(normalized)
        normalized.setdefault("narrative", normalized["narrative_report"])
        trade_idea = normalized.get("trade_idea")
        if isinstance(trade_idea, dict):
            normalized.setdefault("action", trade_idea.get("action", Action.WAIT.value))
        else:
            normalized.setdefault("action", Action.WAIT.value)
        if "STALE_DATA" in normalized["warnings"]:
            normalized["action"] = Action.WAIT.value
            if isinstance(normalized.get("trade_idea"), dict):
                normalized["trade_idea"] = self._force_wait(normalized["trade_idea"], "STALE_DATA")
            if isinstance(normalized.get("gate_result"), dict):
                normalized["gate_result"] = self._force_gate_failure(normalized["gate_result"], "STALE_DATA")
        normalized.setdefault("gate_result", {})
        normalized.setdefault("data_coverage", {})
        normalized.setdefault("liquidity", {})
        normalized.setdefault("dol_candidates", [])
        normalized.setdefault("ssmt", {})
        normalized.setdefault("confirmation", {})
        normalized.setdefault("reasoning", [])
        return normalized

    def _stale_data_warnings(self, request: AnalysisRequest, market_data: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        candles = market_data["primary"].get(request.execution_timeframe, [])
        if candles and self._is_stale(request.analysis_as_of, candles[-1]["time_utc"], request.execution_timeframe):
            warnings.extend(["STALE_DATA", f"STALE_{request.primary_symbol}_{request.execution_timeframe}"])
        if request.secondary_symbol:
            secondary = market_data["secondary"].get(request.execution_timeframe, [])
            if secondary and self._is_stale(request.analysis_as_of, secondary[-1]["time_utc"], request.execution_timeframe):
                warnings.extend(["SECONDARY_STALE", f"STALE_{request.secondary_symbol}_{request.execution_timeframe}"])
        return self._dedupe(warnings)

    def _is_stale(self, as_of: datetime, last_candle_time: datetime, timeframe: str) -> bool:
        age_seconds = int((as_of - last_candle_time).total_seconds())
        return age_seconds > self._freshness_threshold(timeframe)

    def _force_wait(self, trade_idea: dict[str, Any], reason_code: str) -> dict[str, Any]:
        updated = dict(trade_idea)
        updated["action"] = Action.WAIT.value
        updated["reason_code"] = reason_code
        updated["entry_model"] = None
        updated["reason_wait"] = "Action remains WAIT because market data is stale."
        blocking = list(updated.get("blocking_conditions", []))
        if reason_code not in blocking:
            blocking.insert(0, reason_code)
        updated["blocking_conditions"] = blocking
        return updated

    def _force_gate_failure(self, gate_result: dict[str, Any], reason_code: str) -> dict[str, Any]:
        updated = dict(gate_result)
        failed_reasons = list(updated.get("failed_reasons", []))
        if reason_code not in failed_reasons:
            failed_reasons.insert(0, reason_code)
        updated["passed"] = False
        updated["failed_reasons"] = failed_reasons
        return updated

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                output.append(value)
        return output

    def _fallback_analysis(self, request: AnalysisRequest, market_data: dict[str, Any]) -> dict[str, Any]:
        warnings: list[str] = ["STRATEGY_PIPELINE_UNAVAILABLE"]
        data_coverage = self._data_coverage(request, market_data, warnings)
        execution_candles = market_data["primary"].get(request.execution_timeframe, [])
        current_price = execution_candles[-1]["close"] if execution_candles else None
        htf_context = self._build_htf_context(request, market_data, current_price)
        dol_candidates = self._build_dol_candidates(request, market_data, htf_context, current_price)
        selected_dol = dol_candidates[0] if dol_candidates else None
        ssmt = self._detect_ssmt(request, market_data, warnings)
        confirmation = self._detect_confirmation(execution_candles, selected_dol)
        trade_idea, gate_result, active_model, bias = self._build_trade_idea(
            data_coverage=data_coverage,
            htf_context=htf_context,
            selected_dol=selected_dol,
            confirmation=confirmation,
            ssmt=ssmt,
        )
        liquidity = {
            "recently_taken": self._recently_taken_liquidity(execution_candles),
            "next_dol": selected_dol,
        }
        confidence = selected_dol.get("confidence", "unavailable") if selected_dol else "unavailable"
        result = {
            "primary_symbol": request.primary_symbol,
            "secondary_symbol": request.secondary_symbol,
            "execution_timeframe": request.execution_timeframe,
            "context_timeframes": request.context_timeframes,
            "analysis_as_of": iso_utc(request.analysis_as_of),
            "rule_version": RULE_VERSION,
            "market_state": self._market_state(confirmation),
            "active_model": active_model,
            "bias": bias,
            "action": trade_idea["action"],
            "data_coverage": data_coverage,
            "time_context": self._time_context(request.analysis_as_of),
            "htf_context": htf_context,
            "liquidity": liquidity,
            "dol_candidates": dol_candidates,
            "ssmt": ssmt,
            "confirmation": confirmation,
            "trade_idea": trade_idea,
            "gate_result": gate_result,
            "confidence": confidence,
            "reasoning": self._reasoning(htf_context, selected_dol, ssmt, confirmation, trade_idea),
            "warnings": warnings,
        }
        result["narrative_report"] = build_narrative(result)
        return result

    def _data_coverage(self, request: AnalysisRequest, market_data: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
        missing = []
        stale = []
        primary_counts = {
            timeframe: len(candles)
            for timeframe, candles in market_data["primary"].items()
        }
        if primary_counts.get(request.execution_timeframe, 0) < MINIMUMS["M15"]:
            missing.append({"symbol": request.primary_symbol, "timeframe": request.execution_timeframe, "reason": "INSUFFICIENT_DATA"})
            warnings.append("INSUFFICIENT_DATA")
        if primary_counts.get("H1", 0) < MINIMUMS["H1"]:
            missing.append({"symbol": request.primary_symbol, "timeframe": "H1", "reason": "MISSING_HTF_CONTEXT"})
            warnings.append("MISSING_HTF_CONTEXT")
        h4_count = primary_counts.get("H4", 0)
        degraded_mode = h4_count < MINIMUMS["H4"] and primary_counts.get("H1", 0) >= MINIMUMS["H1"]
        if h4_count < MINIMUMS["H4"]:
            missing.append({"symbol": request.primary_symbol, "timeframe": "H4", "reason": "H4_UNAVAILABLE"})
            warnings.append("H4_UNAVAILABLE")
        if primary_counts.get("D1", 0) < MINIMUMS["D1"]:
            warnings.append("D1_MISSING")
        status = "complete"
        if degraded_mode:
            status = "degraded"
            warnings.append("DEGRADED_H1_ONLY_MODE")
        if any(item["reason"] in {"INSUFFICIENT_DATA", "MISSING_HTF_CONTEXT"} for item in missing):
            status = "incomplete"
        return {
            "status": status,
            "missing": missing,
            "stale": stale,
            "degraded_mode": degraded_mode,
            "counts": {str(key): value for key, value in market_data["counts"].items()},
        }

    def _build_htf_context(self, request: AnalysisRequest, market_data: dict[str, Any], current_price: float | None) -> dict[str, Any]:
        source_timeframe = None
        source_candles: list[dict[str, Any]] = []
        for timeframe, minimum in (("H4", MINIMUMS["H4"]), ("H1", MINIMUMS["H1"])):
            candles = market_data["primary"].get(timeframe, [])
            if len(candles) >= minimum:
                source_timeframe = timeframe
                source_candles = candles[-minimum:]
                break
        if not source_candles or current_price is None:
            return {
                "dealing_range_high": None,
                "dealing_range_low": None,
                "equilibrium": None,
                "current_position": "unknown",
                "dol_direction": "unknown",
                "source_timeframe": source_timeframe,
            }
        high = max(candle["high"] for candle in source_candles)
        low = min(candle["low"] for candle in source_candles)
        equilibrium = (high + low) / 2
        band = (high - low) * 0.05
        if current_price > equilibrium + band:
            position = "premium"
            dol_direction = "sellside"
        elif current_price < equilibrium - band:
            position = "discount"
            dol_direction = "buyside"
        else:
            position = "equilibrium"
            dol_direction = "unclear"
        return {
            "dealing_range_high": round(high, 5),
            "dealing_range_low": round(low, 5),
            "equilibrium": round(equilibrium, 5),
            "current_position": position,
            "dol_direction": dol_direction,
            "source_timeframe": source_timeframe,
        }

    def _build_dol_candidates(
        self,
        request: AnalysisRequest,
        market_data: dict[str, Any],
        htf_context: dict[str, Any],
        current_price: float | None,
    ) -> list[dict[str, Any]]:
        if current_price is None or htf_context.get("dol_direction") in {None, "unknown", "unclear"}:
            return []
        direction = htf_context["dol_direction"]
        d1 = market_data["primary"].get("D1", [])
        candidates = []
        if len(d1) >= 2:
            previous_day = d1[-2]
            if direction == "sellside":
                candidates.append(self._candidate("previous_day_low", "D1", "ERL", direction, previous_day["low"], 75))
            else:
                candidates.append(self._candidate("previous_day_high", "D1", "ERL", direction, previous_day["high"], 75))
        boundary_price = (
            htf_context.get("dealing_range_low") if direction == "sellside" else htf_context.get("dealing_range_high")
        )
        if boundary_price is not None:
            candidates.append(self._candidate("active_range_boundary", htf_context.get("source_timeframe") or "H1", "ERL", direction, boundary_price, 65))
        for candidate in candidates:
            candidate["distance"] = round(abs(candidate["price"] - current_price), 5)
            if candidate["distance"] > 0 and isfinite(candidate["distance"]):
                candidate["score"] = max(0, candidate["score"] - min(15, int(candidate["distance"] // 100)))
            candidate["confidence"] = self._confidence(candidate["score"])
        return sorted(candidates, key=lambda item: (item["score"], item["liquidity_type"] == "ERL", -item["distance"]), reverse=True)

    def _candidate(self, label: str, timeframe: str, liquidity_type: str, direction: str, price: float, score: int) -> dict[str, Any]:
        return {
            "label": label,
            "timeframe": timeframe,
            "liquidity_type": liquidity_type,
            "direction": direction,
            "price": round(float(price), 5),
            "score": score,
            "confidence": self._confidence(score),
            "reasoning": [
                f"{liquidity_type} candidate aligned with {direction} DOL",
                f"Candidate sourced from {timeframe}",
            ],
        }

    def _detect_ssmt(self, request: AnalysisRequest, market_data: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
        primary = market_data["primary"].get(request.execution_timeframe, [])
        secondary = market_data["secondary"].get(request.execution_timeframe, [])
        if request.secondary_symbol is None or not secondary:
            warnings.append("SSMT_UNAVAILABLE")
            return {"available": False, "detected": False, "type": None, "quality": "unavailable", "sync_status": "secondary_missing"}
        if len(primary) < 2 or len(secondary) < 2:
            warnings.append("SSMT_UNAVAILABLE")
            return {"available": False, "detected": False, "type": None, "quality": "unavailable", "sync_status": "insufficient_data"}
        primary_latest = primary[-1]
        secondary_latest = secondary[-1]
        diff = abs((primary_latest["time_utc"] - secondary_latest["time_utc"]).total_seconds())
        if diff > SSMT_ALIGNMENT_TOLERANCE_SECONDS:
            warnings.append("SSMT_TIMESTAMP_MISMATCH")
            return {"available": False, "detected": False, "type": None, "quality": "unavailable", "sync_status": "timestamp_mismatch"}
        age = (request.analysis_as_of - secondary_latest["time_utc"]).total_seconds()
        if age > SECONDARY_STALE_AFTER_SECONDS:
            warnings.append("SECONDARY_STALE")
            return {"available": False, "detected": False, "type": None, "quality": "unavailable", "sync_status": "secondary_stale"}
        bullish = primary[-1]["low"] < primary[-2]["low"] and secondary[-1]["low"] >= secondary[-2]["low"]
        bearish = primary[-1]["high"] > primary[-2]["high"] and secondary[-1]["high"] <= secondary[-2]["high"]
        ssmt_type = "bullish" if bullish else "bearish" if bearish else None
        return {
            "available": True,
            "detected": bool(ssmt_type),
            "type": ssmt_type,
            "quality": "medium" if ssmt_type else "none",
            "sync_status": "aligned",
            "divergence_point": iso_utc(primary_latest["time_utc"]) if ssmt_type else None,
        }

    def _detect_confirmation(self, candles: list[dict[str, Any]], selected_dol: dict[str, Any] | None) -> dict[str, bool]:
        if len(candles) < 20:
            return {"sweep": False, "displacement": False, "mss": False, "fvg": False}
        latest = candles[-1]
        previous_window = candles[-17:-1]
        direction = selected_dol.get("direction") if selected_dol else None
        buyside_sweep = latest["high"] > max(candle["high"] for candle in previous_window)
        sellside_sweep = latest["low"] < min(candle["low"] for candle in previous_window)
        sweep = buyside_sweep if direction == "sellside" else sellside_sweep if direction == "buyside" else buyside_sweep or sellside_sweep
        avg_body = sum(abs(candle["close"] - candle["open"]) for candle in candles[-21:-1]) / 20
        latest_body = abs(latest["close"] - latest["open"])
        displacement = avg_body > 0 and latest_body >= 1.5 * avg_body
        if direction == "sellside":
            mss = latest["close"] < min(candle["low"] for candle in candles[-8:-1])
        elif direction == "buyside":
            mss = latest["close"] > max(candle["high"] for candle in candles[-8:-1])
        else:
            mss = False
        last_three = candles[-3:]
        bullish_fvg = last_three[0]["high"] < last_three[2]["low"]
        bearish_fvg = last_three[0]["low"] > last_three[2]["high"]
        fvg = bearish_fvg if direction == "sellside" else bullish_fvg if direction == "buyside" else bullish_fvg or bearish_fvg
        return {"sweep": bool(sweep), "displacement": bool(displacement), "mss": bool(mss), "fvg": bool(fvg)}

    def _build_trade_idea(
        self,
        data_coverage: dict[str, Any],
        htf_context: dict[str, Any],
        selected_dol: dict[str, Any] | None,
        confirmation: dict[str, bool],
        ssmt: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], str | None, str]:
        direction = selected_dol.get("direction") if selected_dol else None
        bias = "SELL" if direction == "sellside" else "BUY" if direction == "buyside" else "WAIT"
        active_model = f"IRL_TO_ERL_{bias}" if bias in {"BUY", "SELL"} else None
        required = ["sweep", "displacement", "mss", "fvg"]
        present = [name for name in required if confirmation.get(name)]
        failed_reasons = []
        blocking = []
        if data_coverage["status"] == "incomplete":
            failed_reasons.append(ReasonCode.MISSING_HTF_CONTEXT.value)
        if selected_dol is None:
            failed_reasons.append(ReasonCode.UNCLEAR_DOL.value)
        elif selected_dol.get("score", 0) < 60:
            failed_reasons.append(ReasonCode.UNCLEAR_DOL.value)
        if htf_context.get("current_position") == "equilibrium" and (not selected_dol or selected_dol.get("score", 0) < 80):
            failed_reasons.append(ReasonCode.UNCLEAR_DOL.value)
        for item in required:
            if not confirmation.get(item):
                reason = {
                    "sweep": ReasonCode.MISSING_SWEEP.value,
                    "displacement": ReasonCode.MISSING_DISPLACEMENT.value,
                    "mss": ReasonCode.MISSING_MSS.value,
                    "fvg": ReasonCode.MISSING_FVG.value,
                }[item]
                failed_reasons.append(reason)
                blocking.append(item)
        failed_reasons = list(dict.fromkeys(failed_reasons))
        passed = not failed_reasons
        action = bias if passed and bias in {"BUY", "SELL"} else Action.WAIT.value
        reason_code = ReasonCode.GATE_COMPLETE.value if passed else failed_reasons[0]
        take_profit = selected_dol.get("price") if selected_dol else None
        invalidation = None if "mss" in blocking else "opposite side of execution sweep"
        trade_idea = {
            "action": action,
            "reason_code": reason_code,
            "blocking_conditions": blocking,
            "reason_wait": None if passed else self._wait_reason(reason_code, blocking),
            "entry_model": active_model if passed else None,
            "entry_area": None,
            "stop_loss": None,
            "take_profit": take_profit,
            "invalidation": invalidation or "MSS required before entry model becomes valid",
            "ssmt_required": False,
            "ssmt_available": ssmt.get("available", False),
        }
        gate_result = {
            "passed": passed,
            "failed_reasons": failed_reasons,
            "required_confirmations": required,
            "present_confirmations": present,
        }
        return trade_idea, gate_result, active_model, bias

    def _wait_reason(self, reason_code: str, blocking: list[str]) -> str:
        if blocking:
            return f"Action remains WAIT because {', '.join(blocking)} confirmation is missing."
        return f"Action remains WAIT because {reason_code} blocks the trade gate."

    def _recently_taken_liquidity(self, candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(candles) < 17:
            return []
        latest = candles[-1]
        window = candles[-17:-1]
        taken = []
        if latest["high"] > max(candle["high"] for candle in window):
            taken.append({"label": "internal_buyside_liquidity", "timeframe": "M15", "price": round(latest["high"], 5)})
        if latest["low"] < min(candle["low"] for candle in window):
            taken.append({"label": "internal_sellside_liquidity", "timeframe": "M15", "price": round(latest["low"], 5)})
        return taken

    def _time_context(self, analysis_as_of: datetime) -> dict[str, Any]:
        hour = analysis_as_of.astimezone(timezone.utc).hour
        if 0 <= hour < 7:
            session = "Asia"
        elif 7 <= hour < 12:
            session = "London"
        elif 12 <= hour < 21:
            session = "New York"
        else:
            session = "Outside major session"
        killzone = 7 <= hour < 10 or 13 <= hour < 16
        return {"session": session, "killzone": killzone, "valid_time": session != "Outside major session"}

    def _market_state(self, confirmation: dict[str, bool]) -> str:
        if confirmation.get("sweep") and confirmation.get("displacement"):
            return "post_sweep_displacement"
        if confirmation.get("sweep"):
            return "post_sweep"
        return "context_building"

    def _reasoning(
        self,
        htf_context: dict[str, Any],
        selected_dol: dict[str, Any] | None,
        ssmt: dict[str, Any],
        confirmation: dict[str, bool],
        trade_idea: dict[str, Any],
    ) -> list[str]:
        reasoning = [f"HTF price is trading in {htf_context.get('current_position', 'unknown')}"]
        if selected_dol:
            reasoning.append(f"HTF DOL points toward {selected_dol['label']}")
        else:
            reasoning.append("No clear DOL candidate is available")
        if ssmt.get("available") and ssmt.get("detected"):
            reasoning.append(f"{ssmt.get('type')} SSMT detected between XAUUSD and XAGUSD")
        elif not ssmt.get("available"):
            reasoning.append(f"SSMT unavailable because sync status is {ssmt.get('sync_status')}")
        missing = [name for name, present in confirmation.items() if not present]
        if missing:
            reasoning.append(f"Missing M15 confirmation: {', '.join(missing)}")
        reasoning.append(f"Trade gate reason code: {trade_idea.get('reason_code')}")
        return reasoning

    def _confidence(self, score: int) -> str:
        if score >= 80:
            return "high"
        if score >= 60:
            return "medium"
        if score >= 40:
            return "low"
        return "unavailable"

    def _freshness_threshold(self, timeframe: str) -> int:
        return {
            "M5": 10 * 60,
            "M15": 30 * 60,
            "H1": 2 * 60 * 60,
            "H4": 8 * 60 * 60,
            "D1": 48 * 60 * 60,
        }.get(timeframe, 60 * 60)

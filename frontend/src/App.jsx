import React, { useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Check,
  CircleHelp,
  Database,
  FileText,
  GitCompareArrows,
  LoaderCircle,
  RefreshCcw,
  ShieldAlert,
  Target,
  X,
} from "lucide-react";
import { analyzeRequest, sampleAnalysis } from "./sampleAnalysis.js";

const confirmationLabels = {
  sweep: "Sweep",
  displacement: "Displacement",
  mss: "MSS / CHOCH",
  fvg: "FVG",
};

const actionTone = {
  WAIT: "wait",
  BUY: "buy",
  SELL: "sell",
};

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function formatPrice(value) {
  return typeof value === "number" ? value.toFixed(2) : "Unavailable";
}

function formatLabel(value) {
  return String(value ?? "unavailable").replaceAll("_", " ");
}

function formatCoverageItem(item) {
  if (typeof item === "string") {
    return formatLabel(item);
  }
  if (item && typeof item === "object") {
    const parts = [item.symbol, item.timeframe, item.reason ?? item.warning].filter(Boolean);
    return parts.length ? parts.map(formatLabel).join(" ") : JSON.stringify(item);
  }
  return formatLabel(item);
}

function formatList(items) {
  return Array.isArray(items) && items.length ? items.map(formatCoverageItem).join(", ") : "None";
}

function StatusPill({ children, tone = "neutral" }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

function IconButton({ label, onClick, busy, variant = "primary" }) {
  return (
    <button className={`icon-button icon-button-${variant}`} type="button" onClick={onClick} disabled={busy} title={label}>
      {busy ? (
        <LoaderCircle size={18} className="spin" aria-hidden="true" />
      ) : (
        <RefreshCcw size={18} aria-hidden="true" />
      )}
      <span>{label}</span>
    </button>
  );
}

function Panel({ icon: Icon, title, children, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel-header">
        <Icon size={18} aria-hidden="true" />
        <h2>{title}</h2>
      </header>
      {children}
    </section>
  );
}

function Metric({ label, value, sub }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {sub ? <small>{sub}</small> : null}
    </div>
  );
}

function DataStatus({ analysis }) {
  const coverage = analysis.data_coverage ?? {};
  const liveSource = analysis.market_data_source;
  const lastCandles = coverage.last_candles ?? {};
  const counts = coverage.counts ?? {};
  const missing = coverage.missing ?? [];
  const stale = coverage.stale ?? [];

  return (
    <Panel icon={Database} title="Data Status">
      <div className="status-row">
        <StatusPill tone={coverage.status === "complete" ? "good" : "warn"}>
          {formatLabel(coverage.status)}
        </StatusPill>
        {coverage.degraded_mode ? <StatusPill tone="warn">Degraded mode</StatusPill> : null}
        {liveSource ? <StatusPill tone="good">{liveSource.provider} {liveSource.exchange}</StatusPill> : null}
      </div>
      {liveSource?.series?.length ? (
        <div className="source-strip">
          {liveSource.series.map((item) => (
            <span key={`${item.symbol}-${item.timeframe}`}>
              {item.symbol} {item.timeframe}: {item.rows_imported} rows
            </span>
          ))}
        </div>
      ) : null}
      <div className="feed-list">
        {Object.entries(lastCandles).map(([key, time]) => (
          <div className="feed-row" key={key}>
            <span>{key.replace("_", " ")}</span>
            <time>{time}</time>
          </div>
        ))}
      </div>
      {Object.keys(lastCandles).length === 0 && Object.keys(counts).length > 0 ? (
        <div className="feed-list">
          {Object.entries(counts).map(([key, count]) => (
            <div className="feed-row" key={key}>
              <span>{key.replace("_", " ")}</span>
              <time>{count} candles</time>
            </div>
          ))}
        </div>
      ) : null}
      <div className="compact-list">
        <span>Missing: {formatList(missing)}</span>
        <span>Stale: {formatList(stale)}</span>
      </div>
    </Panel>
  );
}

function HtfContext({ analysis }) {
  const htf = analysis.htf_context ?? {};
  const phase = htf.candle_phase ?? {};
  const directionLiquidity = htf.direction_liquidity ?? {};
  const activeDirectionLevel = directionLiquidity.active_level ?? {};
  const rangeSize = htf.dealing_range_high - htf.dealing_range_low;
  const rangePosition =
    typeof htf.current_price === "number" && rangeSize > 0
      ? clamp(((htf.current_price - htf.dealing_range_low) / rangeSize) * 100, 0, 100)
      : 50;

  return (
    <Panel icon={BarChart3} title="HTF Context">
      <div className="metric-grid">
        <Metric label="Bias" value={analysis.bias} sub={htf.bias_source} />
        <Metric label="Location" value={formatLabel(htf.current_position)} />
        <Metric label="DOL direction" value={formatLabel(htf.dol_direction)} />
        <Metric label="Current / EQ" value={`${formatPrice(htf.current_price)} / ${formatPrice(htf.equilibrium)}`} />
        <Metric label="HTF candle" value={phase.pattern ?? "Unavailable"} sub={formatLabel(phase.current_leg)} />
        <Metric
          label="HTF O/H/L/C"
          value={`${formatPrice(phase.open)} / ${formatPrice(phase.high)} / ${formatPrice(phase.low)} / ${formatPrice(phase.close)}`}
        />
        <Metric
          label="Direction layer"
          value={formatLabel(directionLiquidity.dominant_direction)}
          sub={`${activeDirectionLevel.parent_timeframe ?? "NA"} > ${activeDirectionLevel.irl_erl_timeframe ?? "NA"} > ${(
            activeDirectionLevel.direction_timeframes ?? []
          ).join("/") || "NA"}`}
        />
      </div>
      <div className="range-track" aria-label="Dealing range">
        <span>{formatPrice(htf.dealing_range_low)}</span>
        <div style={{ "--range-position": `${rangePosition}%` }}>
          <i />
        </div>
        <span>{formatPrice(htf.dealing_range_high)}</span>
      </div>
    </Panel>
  );
}

function DolPanel({ analysis }) {
  const selected = analysis.liquidity?.next_dol ?? {};
  const candidates = analysis.dol_candidates ?? [];
  const runnerUp = candidates.find((candidate) => candidate.label !== selected.label) ?? candidates[1];

  return (
    <Panel icon={Target} title="Draw On Liquidity">
      <div className="dol-selected">
        <div>
          <span>Selected DOL</span>
          <strong>{formatLabel(selected.label)}</strong>
          <small>
            {selected.timeframe} {selected.liquidity_type} at {formatPrice(selected.price)}
          </small>
        </div>
        <div className="score-badge">
          <strong>{selected.score ?? "NA"}</strong>
          <span>{selected.confidence ?? "unavailable"}</span>
        </div>
      </div>
      {runnerUp ? (
        <div className="runner-up">
          <span>Runner-up</span>
          <strong>{formatLabel(runnerUp.label)}</strong>
          <small>
            {runnerUp.score} points, {runnerUp.timeframe} {runnerUp.liquidity_type}
          </small>
        </div>
      ) : null}
      <ul className="reason-list">
        {(selected.reasoning ?? analysis.reasoning ?? []).map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
    </Panel>
  );
}

function Checklist({ analysis }) {
  const confirmation = analysis.confirmation ?? {};
  const blocking = new Set(analysis.trade_idea?.blocking_conditions ?? []);

  return (
    <Panel icon={Activity} title="M15 Checklist">
      <div className="checklist">
        {Object.entries(confirmationLabels).map(([key, label]) => {
          const present = Boolean(confirmation[key]);
          return (
            <div className={`check-row ${present ? "present" : "missing"}`} key={key}>
              {present ? <Check size={18} aria-hidden="true" /> : <X size={18} aria-hidden="true" />}
              <span>{label}</span>
              {blocking.has(key) ? <StatusPill tone="bad">Blocking</StatusPill> : null}
            </div>
          );
        })}
      </div>
      <div className="compact-list">
        <span>Present: {analysis.gate_result?.present_confirmations?.join(", ") || "None"}</span>
        <span>Missing: {analysis.gate_result?.failed_reasons?.join(", ") || "None"}</span>
      </div>
    </Panel>
  );
}

function SsmtPanel({ analysis }) {
  const ssmt = analysis.ssmt ?? {};
  const tone = !ssmt.available ? "warn" : ssmt.detected ? "good" : "neutral";

  return (
    <Panel icon={GitCompareArrows} title="SSMT">
      <div className="ssmt-grid">
        <Metric label="Availability" value={ssmt.available ? "Available" : "Unavailable"} />
        <Metric label="Detected" value={ssmt.detected ? "Yes" : "No"} />
        <Metric label="Type" value={formatLabel(ssmt.type)} />
        <Metric label="Sync" value={formatLabel(ssmt.sync_status)} />
        <Metric label="Sequence" value={formatLabel(ssmt.sequence)} />
        <Metric label="Quarters" value={`${ssmt.reference_quarter ?? "NA"} > ${ssmt.primary_quarter ?? "NA"}`} />
      </div>
      <StatusPill tone={ssmt.magneto ? "warn" : tone}>
        {ssmt.magneto ? `Magneto at ${formatPrice(ssmt.magneto_level)}` : ssmt.quality ? `${ssmt.quality} quality` : "No divergence"}
      </StatusPill>
    </Panel>
  );
}

function TradeIdea({ analysis }) {
  const idea = analysis.trade_idea ?? {};
  const tone = actionTone[idea.action] ?? "neutral";
  const gatePassed = Boolean(analysis.gate_result?.passed);
  const failedReasons = analysis.gate_result?.failed_reasons ?? [];

  return (
    <Panel icon={ShieldAlert} title="Trade Idea" className="trade-panel">
      <div className="trade-head">
        <div>
          <span>Rule output</span>
          <strong className={`action action-${tone}`}>{idea.action}</strong>
        </div>
        <StatusPill tone={idea.reason_code === "GATE_COMPLETE" ? "good" : "warn"}>
          {idea.reason_code}
        </StatusPill>
      </div>
      <p>{idea.reason_wait ?? "Gate complete."}</p>
      <div className="gate-strip">
        <StatusPill tone={gatePassed ? "good" : "bad"}>{gatePassed ? "Gate complete" : "Gate blocked"}</StatusPill>
        <span>{failedReasons.length ? failedReasons.map(formatLabel).join(", ") : "All required confirmations present"}</span>
      </div>
      <div className="metric-grid two">
        <Metric label="Take profit" value={formatPrice(idea.take_profit)} />
        <Metric label="Invalidation" value={idea.invalidation ?? formatPrice(idea.stop_loss)} />
      </div>
    </Panel>
  );
}

function Narrative({ analysis }) {
  const narrative = analysis.narrative ?? analysis.reasoning?.join(" ");
  const warnings = analysis.warnings ?? [];

  return (
    <Panel icon={FileText} title="Narrative" className="narrative-panel">
      <p>{narrative}</p>
      {warnings.length ? (
        <div className="warning-list">
          {warnings.map((warning) => (
            <span key={warning}>
              <AlertTriangle size={16} aria-hidden="true" />
              {warning}
            </span>
          ))}
        </div>
      ) : (
        <span className="quiet-line">
          <CircleHelp size={16} aria-hidden="true" />
          No data warnings
        </span>
      )}
    </Panel>
  );
}

export default function App() {
  const [analysis, setAnalysis] = useState(sampleAnalysis);
  const [apiBase, setApiBase] = useState("http://127.0.0.1:8000");
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");

  const subtitle = useMemo(
    () =>
      `${analysis.primary_symbol}/${analysis.secondary_symbol} ${analysis.execution_timeframe} as of ${analysis.analysis_as_of}`,
    [analysis],
  );

  async function refreshAnalysis() {
    setBusyAction("analyze");
    setError("");
    try {
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(analyzeRequest),
      });
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }
      const nextAnalysis = await response.json();
      setAnalysis(nextAnalysis);
    } catch (refreshError) {
      setError(refreshError.message);
      setAnalysis(sampleAnalysis);
    } finally {
      setBusyAction("");
    }
  }

  async function refreshTradingView() {
    setBusyAction("tradingview");
    setError("");
    try {
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/api/tradingview/analyze`, {
        method: "POST",
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `TradingView API returned ${response.status}`);
      }
      const nextAnalysis = await response.json();
      setAnalysis(nextAnalysis);
    } catch (refreshError) {
      setError(refreshError.message);
    } finally {
      setBusyAction("");
    }
  }

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <StatusPill tone={analysis.action === "WAIT" ? "warn" : "good"}>{analysis.action}</StatusPill>
          <h1>HTF/M15 Discipline Engine</h1>
          <p>{subtitle}. WAIT remains valid until HTF context and M15 execution gates agree.</p>
        </div>
        <div className="api-controls">
          <label>
            <span>API</span>
            <input value={apiBase} onChange={(event) => setApiBase(event.target.value)} />
          </label>
          <IconButton
            label="Analyze DB"
            onClick={refreshAnalysis}
            busy={busyAction === "analyze"}
            variant="secondary"
          />
          <IconButton
            label="TradingView Live"
            onClick={refreshTradingView}
            busy={busyAction === "tradingview"}
          />
        </div>
      </section>

      {error ? (
        <div className="api-error">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>{error}; showing fixture analysis.</span>
        </div>
      ) : null}

      <section className="dashboard-grid">
        <TradeIdea analysis={analysis} />
        <DataStatus analysis={analysis} />
        <HtfContext analysis={analysis} />
        <DolPanel analysis={analysis} />
        <Checklist analysis={analysis} />
        <SsmtPanel analysis={analysis} />
        <Narrative analysis={analysis} />
      </section>
    </main>
  );
}

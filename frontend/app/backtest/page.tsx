"use client";

import Link from "next/link";
import { Alert, Button, Card, Empty, InputNumber, Select, Spin, Tag, message } from "antd";
import { useEffect, useState } from "react";

const API_ROOT = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const YEARS = Array.from({ length: 15 }, (_, index) => 2026 + index);
type ImportRecord = {
  id: number;
  source_filename: string;
  symbol: string;
  timeframe_minutes: number;
  row_count: number;
  first_timestamp_utc: string | null;
  last_timestamp_utc: string | null;
  status: string;
};
type BacktestRun = {
  id: number;
  status: "running" | "completed" | "failed";
  name: string;
  timeframe_minutes: number;
  parameters: Record<string, unknown>;
  event_windows: number;
  windows_with_data: number;
  baseline_description: string;
  prevents_lookahead: boolean;
  metrics: {
    mean_max_upward_move: number | null;
    mean_max_downward_move: number | null;
    mean_price_range: number | null;
    mean_volatility: number | null;
    reversals: number;
    sideways_windows: number;
  };
  directional_accuracy: number | null;
};
type EventMetric = {
  id: number;
  planet_1: string;
  planet_2: string;
  aspect_name: string;
  aspect_angle_degrees: number;
  exact_time_local: string;
  max_upward_move: number | null;
  max_downward_move: number | null;
  price_range: number | null;
  volatility: number | null;
  reversal_observed: number | null;
  time_to_reversal_seconds: number | null;
  sideways_observed: number | null;
  baseline_metrics: Record<string, unknown>;
  observed_metrics: Record<string, unknown>;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init?.headers : { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Local API error (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function percent(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(2)}%`;
}

export default function MarketBacktestPage() {
  const [imports, setImports] = useState<ImportRecord[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [symbol, setSymbol] = useState("NIFTY");
  const [timeframe, setTimeframe] = useState(1);
  const [importing, setImporting] = useState(false);
  const [year, setYear] = useState(2026);
  const [horizon, setHorizon] = useState(60);
  const [reversalThreshold, setReversalThreshold] = useState<number | null>(0.25);
  const [sidewaysThreshold, setSidewaysThreshold] = useState<number | null>(0.2);
  const [planet, setPlanet] = useState<string | undefined>();
  const [aspect, setAspect] = useState<string | undefined>();
  const [run, setRun] = useState<BacktestRun | null>(null);
  const [rows, setRows] = useState<EventMetric[]>([]);
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [messageApi, contextHolder] = message.useMessage();

  async function refreshImports() {
    setImports(await api<ImportRecord[]>("/api/market/imports"));
  }

  useEffect(() => {
    void refreshImports().catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Could not load market imports"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!run || run.status !== "running") return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await api<BacktestRun>(`/api/backtests/${run.id}`);
        setRun(latest);
        if (latest.status === "completed") {
          const resultRows = await api<EventMetric[]>(`/api/backtests/${run.id}/metrics?limit=1000`);
          setRows(resultRows);
          setRunning(false);
          messageApi.success(`Backtest complete: ${latest.windows_with_data} event windows had candles`);
        } else if (latest.status === "failed") {
          setRunning(false);
          setError("Backtest failed. Confirm the selected year and imported candle coverage.");
        }
      } catch (requestError) {
        setRunning(false);
        setError(requestError instanceof Error ? requestError.message : "Could not read backtest status");
      }
    }, 1700);
    return () => window.clearInterval(timer);
  }, [run?.id, run?.status, messageApi]);

  async function importCsv() {
    if (!file) { setError("Choose an OHLC CSV file first"); return; }
    setImporting(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("symbol", symbol);
      form.append("timeframe_minutes", String(timeframe));
      form.append("timezone_name", "Asia/Kolkata");
      const imported = await api<{ row_count: number; symbol: string; timeframe_minutes: number }>("/api/market/import", { method: "POST", body: form });
      await refreshImports();
      setFile(null);
      const picker = document.getElementById("market-csv") as HTMLInputElement | null;
      if (picker) picker.value = "";
      messageApi.success(`Imported ${imported.row_count.toLocaleString()} ${imported.timeframe_minutes}-minute ${imported.symbol} candles`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "CSV import failed");
    } finally {
      setImporting(false);
    }
  }

  async function startRun() {
    setRunning(true);
    setError(null);
    setRows([]);
    try {
      const created = await api<{ id: number; status: BacktestRun["status"]; year: number; symbol: string }>("/api/backtests", {
        method: "POST",
        body: JSON.stringify({
          symbol,
          timeframe_minutes: timeframe,
          year,
          horizon_minutes: horizon,
          reversal_threshold_percent: reversalThreshold,
          sideways_threshold_percent: sidewaysThreshold,
          planet: planet ?? null,
          aspect: aspect ?? null,
        }),
      });
      setRun({ id: created.id, status: created.status, name: `${created.symbol} ${created.year}`, timeframe_minutes: timeframe, parameters: {}, event_windows: 0, windows_with_data: 0, baseline_description: "", prevents_lookahead: true, metrics: { mean_max_upward_move: null, mean_max_downward_move: null, mean_price_range: null, mean_volatility: null, reversals: 0, sideways_windows: 0 }, directional_accuracy: null });
      messageApi.info("Backtest queued");
    } catch (requestError) {
      setRunning(false);
      setError(requestError instanceof Error ? requestError.message : "Could not start the backtest");
    }
  }

  const noDirectionalRules = true;

  return (
    <div className="app-shell">
      {contextHolder}
      <aside className="sidebar">
        <div className="brand-mark">✳</div><div className="brand-copy"><strong>ASTRO</strong><span>MARKET ANALYZER</span></div>
        <div className="nav-label">RESEARCH</div>
        <Link href="/" className="nav-item"><span className="nav-glyph">▦</span>Dashboard</Link>
        <Link href="/calendar" className="nav-item"><span className="nav-glyph">◷</span>Astro Calendar</Link>
        <Link href="/calculator" className="nav-item"><span className="nav-glyph">◈</span>Planetary Calculator</Link>
        <Link href="/timing" className="nav-item"><span className="nav-glyph">⌁</span>Intraday Analyzer</Link>
        <Link href="/backtest" className="nav-item active"><span className="nav-glyph">▤</span>Market Backtesting</Link>
        <Link href="/rules" className="nav-item"><span className="nav-glyph">◇</span>Trader Rulebook</Link>
        <div className="nav-label later-label">ANALYSIS</div>
        <Link href="/reports" className="nav-item"><span className="nav-glyph">↗</span>PDF Reports</Link>
        <div className="sidebar-footer"><span className="status-dot" /> Local research workspace</div>
      </aside>

      <main className="main-content">
        <header className="topbar"><div><div className="crumb">RESEARCH <span>/</span> MARKET STUDY</div><h1>Market Backtesting</h1></div><Tag color="blue">OHLC · Local CSV</Tag></header>
        <section className="intro-row"><div><div className="eyebrow">OBSERVED DATA · HYPOTHESIS TESTING</div><h2>Study historical price behaviour</h2><p>Event windows are outcome measurements. Prior-session controls use only candles that occurred before each event.</p></div></section>
        {error && <Alert className="api-alert" type="error" showIcon message="Market analysis issue" description={error} />}

        <section className="market-top-grid">
          <Card bordered={false} className="import-card">
            <div className="eyebrow">IMPORT MARKET DATA</div><h3>Load an OHLC CSV</h3>
            <div className="market-form-row"><label>Instrument<Select value={symbol} options={[{ value: "NIFTY", label: "NIFTY 50" }, { value: "BANKNIFTY", label: "BANK NIFTY" }]} onChange={setSymbol} /></label><label>Candle size<Select value={timeframe} options={[{ value: 1, label: "1 minute" }, { value: 5, label: "5 minutes" }]} onChange={setTimeframe} /></label></div>
            <label className="upload-field">CSV file<input id="market-csv" type="file" accept=".csv,text/csv" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label>
            <p className="import-hint">Required columns: timestamp (or Date + Time), Open, High, Low, Close. Timestamps without an offset are treated as Asia/Kolkata.</p>
            <Button type="primary" onClick={importCsv} loading={importing} disabled={!file} block>Import CSV</Button>
          </Card>
          <Card bordered={false} className="imports-card">
            <div className="results-heading"><div><div className="eyebrow">LOCAL DATASETS</div><h3>Imported files</h3></div><Button size="small" onClick={() => void refreshImports()} loading={loading}>Refresh</Button></div>
            {imports.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No CSV datasets have been imported" /> : <div className="imports-list">{imports.map((item) => <div className="import-row" key={item.id}><span className="import-symbol">{item.symbol}</span><span className="import-detail">{item.source_filename}<small>{item.row_count.toLocaleString()} rows · {item.timeframe_minutes}m · {item.first_timestamp_utc?.slice(0,10)} → {item.last_timestamp_utc?.slice(0,10)}</small></span><Tag>{item.timeframe_minutes}m</Tag></div>)}</div>}
          </Card>
        </section>

        <section className="backtest-run-card">
          <Card bordered={false}>
            <div className="eyebrow">EVENT WINDOW ANALYSIS</div><h3>Configure a research run</h3>
            <div className="backtest-controls">
              <label>Year<Select value={year} options={YEARS.map((value) => ({ value, label: String(value) }))} onChange={setYear} /></label>
              <label>Instrument<Select value={symbol} options={[{ value: "NIFTY", label: "NIFTY 50" }, { value: "BANKNIFTY", label: "BANK NIFTY" }]} onChange={setSymbol} /></label>
              <label>Timeframe<Select value={timeframe} options={[{ value: 1, label: "1 minute" }, { value: 5, label: "5 minutes" }]} onChange={setTimeframe} /></label>
              <label>Outcome horizon<InputNumber min={1} max={240} value={horizon} onChange={(value) => setHorizon(value ?? 60)} addonAfter="min" /></label>
              <label>Reversal threshold<InputNumber min={0.01} max={50} step={0.05} value={reversalThreshold} onChange={setReversalThreshold} addonAfter="%" /></label>
              <label>Sideways range threshold<InputNumber min={0.01} max={50} step={0.05} value={sidewaysThreshold} onChange={setSidewaysThreshold} addonAfter="%" /></label>
              <label>Planet filter<Select allowClear placeholder="All planets" value={planet} onChange={setPlanet} options={["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"].map((value) => ({ value, label: value }))} /></label>
              <label>Aspect filter<Select allowClear placeholder="All aspects" value={aspect} onChange={setAspect} options={["Conjunction", "Semi-square", "Sextile", "Square", "Trine", "Sesquiquadrate", "Opposition"].map((value) => ({ value, label: value }))} /></label>
            </div>
            <div className="backtest-action-row"><div className="lookahead-pill"><span className="status-dot" /> Prior-only baseline · No directional signal provided</div><Button type="primary" onClick={startRun} loading={running} disabled={run?.status === "running"}>Run event study</Button></div>
          </Card>
        </section>

        {run && <section className="backtest-results">
          <div className="results-heading"><div><div className="eyebrow">RESULTS · {run.name}</div><h2>{run.status === "running" ? "Calculating event windows" : "Observed event-window metrics"}</h2></div><Tag color={run.status === "completed" ? "green" : run.status === "failed" ? "red" : "blue"}>{run.status}</Tag></div>
          {run.status === "running" ? <div className="calc-loading"><Spin /><span>Matching event times to imported candles and prior sessions…</span></div> : run.status === "failed" ? <Alert type="error" message="Backtest failed" description="Check the API logs for the failed run details." /> : <>
            <div className="backtest-stats"><Card bordered={false}><StatisticLike label="Event windows" value={run.event_windows} /><small>{run.windows_with_data} with candle coverage</small></Card><Card bordered={false}><StatisticLike label="Mean max upward" value={percent(run.metrics.mean_max_upward_move)} /></Card><Card bordered={false}><StatisticLike label="Mean max downward" value={percent(run.metrics.mean_max_downward_move)} /></Card><Card bordered={false}><StatisticLike label="Mean window range" value={percent(run.metrics.mean_price_range)} /></Card><Card bordered={false}><StatisticLike label="Directional accuracy" value={noDirectionalRules ? "N/A" : "—"} /><small>No source direction labels</small></Card></div>
            <Card bordered={false} className="metrics-table-card"><div className="eyebrow">INDIVIDUAL EVENTS</div><div className="result-table-wrap"><table className="result-table"><thead><tr><th>Exact event (IST)</th><th>Pair · Aspect</th><th>Max up</th><th>Max down</th><th>Range</th><th>Prior mean range</th><th>Reversal</th></tr></thead><tbody>{rows.map((item) => <tr key={item.id}><td>{item.exact_time_local ? new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "short", timeStyle: "short" }).format(new Date(item.exact_time_local)) : "—"}</td><td>{item.planet_1} × {item.planet_2}<small className="table-sub">{item.aspect_name} {item.aspect_angle_degrees}°</small></td><td>{percent(item.max_upward_move)}</td><td>{percent(item.max_downward_move)}</td><td>{percent(item.price_range)}</td><td>{percent(item.baseline_metrics.mean_price_range as number | null)}</td><td>{item.reversal_observed === null ? "Not set" : item.reversal_observed ? `Yes · ${Math.round((item.time_to_reversal_seconds ?? 0) / 60)}m` : "No"}</td></tr>)}</tbody></table></div><p className="baseline-description">{run.baseline_description} Maximum {rows.length} rows shown. Post-event windows are hindsight outcomes, not trading inputs.</p></Card>
          </>}
        </section>}
      </main>
    </div>
  );
}

function StatisticLike({ label, value }: { label: string; value: number | string }) {
  return <div className="simple-stat"><span>{label}</span><strong>{value}</strong></div>;
}

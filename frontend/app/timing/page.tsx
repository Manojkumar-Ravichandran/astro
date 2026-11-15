"use client";

import Link from "next/link";
import { Alert, Button, Card, Empty, InputNumber, Select, Spin, Tag, message } from "antd";
import { useEffect, useMemo, useState } from "react";

const API_ROOT = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const METHODS = [
  { value: "session_open_interval", label: "Fixed interval from market open" },
  { value: "aspect_time_interval", label: "Fixed interval from exact aspect" },
  { value: "session_fraction", label: "Equal session fractions · Gann-style candidate" },
  { value: "best_fit_repeating_interval", label: "Best-fit repeating interval" },
];
type Observation = {
  id: number;
  event_date: string;
  planet_1: string;
  planet_2: string;
  source_aspect_label: string;
  source_angle_degrees: number;
  prediction_text: string | null;
  source_title: string;
  published_times: Array<{ id: number; time: string; timezone: string }>;
};
type TimingResult = {
  comparison_id: number;
  method: string;
  formula_parameters: Record<string, unknown>;
  exact_aspect_time: string | null;
  candidate_times: string[];
  comparisons: Array<{ published_time: string; candidate_time: string | null; error_minutes: number | null; absolute_error_minutes?: number }>;
  mean_absolute_error_minutes: number;
  root_mean_square_error_minutes: number;
  random_phase_baseline_rmse_minutes: number;
  training_note: string;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Local API error (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export default function IntradayAnalyzerPage() {
  const [observations, setObservations] = useState<Observation[]>([]);
  const [selectedId, setSelectedId] = useState<number | undefined>();
  const [method, setMethod] = useState(METHODS[0].value);
  const [interval, setInterval] = useState(65);
  const [subdivisions, setSubdivisions] = useState(6);
  const [minimum, setMinimum] = useState(50);
  const [maximum, setMaximum] = useState(90);
  const [result, setResult] = useState<TimingResult | null>(null);
  const [history, setHistory] = useState<Array<{ id: number; method: string; calculated_at: string; result: TimingResult }>>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messageApi, contextHolder] = message.useMessage();

  const selected = useMemo(() => observations.find((observation) => observation.id === selectedId) ?? null, [observations, selectedId]);

  useEffect(() => {
    void api<Observation[]>("/api/trader/observations")
      .then((items) => { setObservations(items); setSelectedId(items[0]?.id); setError(null); })
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Could not load source observations"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedId) { setHistory([]); return; }
    void api<typeof history>(`/api/timing/comparisons?published_event_id=${selectedId}`)
      .then(setHistory)
      .catch(() => setHistory([]));
  }, [selectedId, result?.comparison_id]);

  async function analyze() {
    if (!selected) return;
    setRunning(true);
    setError(null);
    try {
      const analysis = await api<TimingResult>("/api/timing/analyze", {
        method: "POST",
        body: JSON.stringify({
          published_event_id: selected.id,
          method,
          interval_minutes: interval,
          minimum_interval_minutes: minimum,
          maximum_interval_minutes: maximum,
          subdivisions,
          market_open: "09:15",
          market_close: "15:30",
          timezone: "Asia/Kolkata",
        }),
      });
      setResult(analysis);
      messageApi.success("Timing candidate compared with the published clock times");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Timing comparison failed");
    } finally {
      setRunning(false);
    }
  }

  function openHistory(entry: { result: TimingResult }) {
    setResult(entry.result);
    setMethod(entry.result.method);
  }

  return (
    <div className="app-shell">
      {contextHolder}
      <aside className="sidebar">
        <div className="brand-mark">✳</div><div className="brand-copy"><strong>ASTRO</strong><span>MARKET ANALYZER</span></div>
        <div className="nav-label">RESEARCH</div>
        <Link href="/" className="nav-item"><span className="nav-glyph">▦</span>Dashboard</Link>
        <Link href="/calendar" className="nav-item"><span className="nav-glyph">◷</span>Astro Calendar</Link>
        <Link href="/calculator" className="nav-item"><span className="nav-glyph">◈</span>Planetary Calculator</Link>
        <Link href="/timing" className="nav-item active"><span className="nav-glyph">⌁</span>Intraday Analyzer</Link>
        <Link href="/backtest" className="nav-item"><span className="nav-glyph">▤</span>Market Backtesting</Link>
        <Link href="/rules" className="nav-item"><span className="nav-glyph">◇</span>Trader Rulebook</Link>
        <div className="nav-label later-label">ANALYSIS</div>
        <Link href="/reports" className="nav-item"><span className="nav-glyph">↗</span>PDF Reports</Link>
        <div className="sidebar-footer"><span className="status-dot" /> Local research workspace</div>
      </aside>

      <main className="main-content">
        <header className="topbar"><div><div className="crumb">RESEARCH <span>/</span> TIMING FORMULAS</div><h1>Intraday Timing Analyzer</h1></div><span className="timezone-chip">◷ &nbsp; Asia / Kolkata</span></header>
        <section className="intro-row"><div><div className="eyebrow">CANDIDATE FORMULAS · SOURCE TIMES STAY UNCHANGED</div><h2>Compare timing hypotheses</h2><p>Each score is measured against the selected trader-published times and the source times are kept as their own records.</p></div></section>
        {error && <Alert className="api-alert" type="error" showIcon message="Timing analysis unavailable" description={error} />}

        <section className="timing-layout">
          <Card bordered={false} className="calculator-form">
            <div className="eyebrow">PUBLISHED SOURCE</div><h3>Choose an observation</h3>
            {loading ? <Spin /> : observations.length === 0 ? <Empty description="No trader timing observations are loaded" /> : <>
              <Select
                value={selectedId}
                onChange={(value) => { setSelectedId(value); setResult(null); }}
                options={observations.map((item) => ({
                  value: item.id,
                  label: `${item.event_date} · ${item.planet_1} × ${item.planet_2} · ${item.source_aspect_label}`,
                }))}
                className="observation-select"
              />
              {selected && <div className="source-times-box"><div className="source-meta">{selected.source_title}</div><div className="source-time-tags">{selected.published_times.map((item) => <Tag key={item.id}>{item.time}</Tag>)}</div><div className="source-pair">Original label: <b>{selected.source_aspect_label}</b> <span>({selected.source_angle_degrees}°)</span></div></div>}
            </>}

            <div className="form-label">Candidate formula</div>
            <Select value={method} options={METHODS} onChange={(value) => setMethod(value)} className="full-select" />
            {method === "best_fit_repeating_interval" ? <div className="interval-fields"><label>From<InputNumber min={5} max={360} value={minimum} onChange={(value) => setMinimum(value ?? 50)} addonAfter="min" /></label><label>To<InputNumber min={5} max={360} value={maximum} onChange={(value) => setMaximum(value ?? 90)} addonAfter="min" /></label></div> : method === "session_fraction" ? <label className="single-number">Session divisions<InputNumber min={2} max={24} value={subdivisions} onChange={(value) => setSubdivisions(value ?? 6)} addonAfter="parts" /></label> : <label className="single-number">Repeating interval<InputNumber min={5} max={360} value={interval} onChange={(value) => setInterval(value ?? 65)} addonAfter="minutes" /></label>}
            <div className="formula-anchor">{method === "session_open_interval" ? "Anchor: 09:15 exchange open" : method === "aspect_time_interval" ? "Anchor: nearest calculated aspect time" : method === "session_fraction" ? "Anchor: 09:15 · 375-minute session divided equally" : "Anchor and interval are fit to the same source times"}</div>
            <Button type="primary" size="large" onClick={analyze} loading={running} disabled={!selected} block>Compare formula</Button>
          </Card>

          <div className="timing-results-column">
            <Card bordered={false} className="timing-score-card">
              {!result ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Choose a source and candidate formula, then compare" /> : <>
                <div className="results-heading"><div><div className="eyebrow">IN-SAMPLE TIMING ERROR</div><h3>{METHODS.find((item) => item.value === result.method)?.label}</h3></div><Tag color={result.root_mean_square_error_minutes < result.random_phase_baseline_rmse_minutes ? "green" : "orange"}>{result.root_mean_square_error_minutes < result.random_phase_baseline_rmse_minutes ? "Below baseline" : "At or above baseline"}</Tag></div>
                <div className="timing-metrics"><div><span>Mean absolute error</span><strong>{result.mean_absolute_error_minutes.toFixed(1)} <small>min</small></strong></div><div><span>RMSE</span><strong>{result.root_mean_square_error_minutes.toFixed(1)} <small>min</small></strong></div><div><span>Random-phase baseline</span><strong>{result.random_phase_baseline_rmse_minutes.toFixed(1)} <small>min</small></strong></div></div>
                {result.exact_aspect_time && <div className="exact-anchor">Nearest exact aspect event: <b>{new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" }).format(new Date(result.exact_aspect_time))} IST</b></div>}
                <div className="candidate-line"><span>Candidate session times</span><div>{result.candidate_times.map((time) => <Tag key={time}>{time}</Tag>)}</div></div>
                <p className="training-note">{result.training_note}</p>
              </>}
            </Card>

            {result && <Card bordered={false} className="timing-matches-card"><div className="eyebrow">PUBLISHED TIME MATCHES</div><h3>Per-time residuals</h3><div className="result-table-wrap"><table className="result-table"><thead><tr><th>Published</th><th>Nearest candidate</th><th>Residual</th></tr></thead><tbody>{result.comparisons.map((row) => <tr key={row.published_time}><td>{row.published_time}</td><td>{row.candidate_time ?? "—"}</td><td>{row.error_minutes === null ? "—" : `${row.error_minutes > 0 ? "+" : ""}${row.error_minutes} min`}</td></tr>)}</tbody></table></div></Card>}
          </div>
        </section>

        <section className="timing-bottom-grid">
          <Card bordered={false}><div className="eyebrow">INTERPRETATION GUARDRAIL</div><h3>Candidate score, not trading evidence</h3><p>A timing formula can fit published clock times by chance. This view reports clock-time error only; it does not measure NIFTY direction, volatility, reversals, or profitability.</p><p>For best-fit intervals, the same selected times are used to choose and score the formula. Compare on separate dates before treating a pattern as reproducible.</p></Card>
          <Card bordered={false}><div className="eyebrow">SAVED COMPARISONS</div><h3>Recent formula runs</h3>{history.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No saved comparisons for this source" /> : <div className="history-list">{history.slice(0, 5).map((entry) => <button type="button" key={entry.id} onClick={() => openHistory(entry)}><span>{METHODS.find((item) => item.value === entry.method)?.label ?? entry.method}</span><b>{entry.result.root_mean_square_error_minutes.toFixed(1)} min RMSE</b></button>)}</div>}</Card>
        </section>
      </main>
    </div>
  );
}

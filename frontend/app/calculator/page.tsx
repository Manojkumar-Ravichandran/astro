"use client";

import Link from "next/link";
import { Alert, Button, Card, Checkbox, Empty, Select, Spin, Tag, message } from "antd";
import { useEffect, useMemo, useState } from "react";

const API_ROOT = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const PLANETS = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"];
const ASPECT_OPTIONS = [
  { name: "Conjunction", angle: 0 }, { name: "Semi-square", angle: 45 },
  { name: "Sextile", angle: 60 }, { name: "Square", angle: 90 },
  { name: "Trine", angle: 120 }, { name: "Sesquiquadrate", angle: 135 },
  { name: "Opposition", angle: 180 },
];
type AstroEvent = {
  id: number;
  planet_1: string;
  planet_2: string;
  aspect_name: string;
  aspect_angle_degrees: number;
  exact_time_local: string;
  exact_time_utc: string;
  longitude_1_degrees: number;
  longitude_2_degrees: number;
  angular_separation_degrees: number;
  orb_before_degrees?: number;
  orb_after_degrees?: number;
  orb_window_minutes?: number;
  calculation_settings?: Record<string, unknown>;
};
type Run = { id: number; status: "running" | "completed" | "failed"; event_count: number; error_message?: string | null };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const result = await response.json().catch(() => null);
    throw new Error(result?.detail ?? `Local API error (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function formatLocal(iso: string) {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "medium", hour12: false,
  }).format(new Date(iso));
}

export default function PlanetaryCalculatorPage() {
  const [planet1, setPlanet1] = useState("Moon");
  const [planet2, setPlanet2] = useState("Venus");
  const [startDate, setStartDate] = useState("2026-01-01");
  const [endDate, setEndDate] = useState("2026-12-31");
  const [aspects, setAspects] = useState(ASPECT_OPTIONS.map((aspect) => aspect.name));
  const [runId, setRunId] = useState<number | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<AstroEvent[]>([]);
  const [selected, setSelected] = useState<AstroEvent | null>(null);
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messageApi, contextHolder] = message.useMessage();

  const selectedPair = useMemo(() => `${planet1}|${planet2}`, [planet1, planet2]);

  useEffect(() => {
    if (!runId || run?.status !== "running") return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await api<Run>(`/api/calculations/runs/${runId}`);
        setRun(latest);
        if (latest.status === "completed") {
          const result = await api<AstroEvent[]>(`/api/calculations/runs/${runId}/events`);
          setEvents(result);
          setSelected(result[0] ?? null);
          setCalculating(false);
          messageApi.success(`${result.length} exact event${result.length === 1 ? "" : "s"} calculated`);
        } else if (latest.status === "failed") {
          setCalculating(false);
          setError(latest.error_message ?? "Calculation failed");
        }
      } catch (requestError) {
        setCalculating(false);
        setError(requestError instanceof Error ? requestError.message : "Could not read calculation status");
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [runId, run?.status, messageApi]);

  async function calculate() {
    setError(null);
    setEvents([]);
    setSelected(null);
    setCalculating(true);
    try {
      const created = await api<Run>("/api/calculations/range", {
        method: "POST",
        body: JSON.stringify({
          start_date: startDate,
          end_date: endDate,
          pairs: [[planet1, planet2]],
          aspects,
          timezone: "Asia/Kolkata",
        }),
      });
      setRunId(created.id);
      setRun(created);
      if (created.status === "completed") {
        const result = await api<AstroEvent[]>(`/api/calculations/runs/${created.id}/events`);
        setEvents(result);
        setSelected(result[0] ?? null);
        setCalculating(false);
      }
    } catch (requestError) {
      setCalculating(false);
      setError(requestError instanceof Error ? requestError.message : "Could not start calculation");
    }
  }

  return (
    <div className="app-shell">
      {contextHolder}
      <aside className="sidebar">
        <div className="brand-mark">✳</div>
        <div className="brand-copy"><strong>ASTRO</strong><span>MARKET ANALYZER</span></div>
        <div className="nav-label">RESEARCH</div>
        <Link href="/" className="nav-item"><span className="nav-glyph">▦</span>Dashboard</Link>
        <Link href="/calendar" className="nav-item"><span className="nav-glyph">◷</span>Astro Calendar</Link>
        <Link href="/calculator" className="nav-item active"><span className="nav-glyph">◈</span>Planetary Calculator</Link>
        <Link href="/timing" className="nav-item"><span className="nav-glyph">⌁</span>Intraday Analyzer</Link>
        <Link href="/backtest" className="nav-item"><span className="nav-glyph">▤</span>Market Backtesting</Link>
        <Link href="/rules" className="nav-item"><span className="nav-glyph">◇</span>Trader Rulebook</Link>
        <div className="nav-label later-label">ANALYSIS</div>
        <Link href="/reports" className="nav-item"><span className="nav-glyph">↗</span>PDF Reports</Link>
        <div className="sidebar-footer"><span className="status-dot" /> Local research workspace</div>
      </aside>

      <main className="main-content">
        <header className="topbar"><div><div className="crumb">RESEARCH <span>/</span> CALCULATOR</div><h1>Planetary Calculator</h1></div><span className="timezone-chip">◷ &nbsp; Asia / Kolkata</span></header>
        <section className="intro-row"><div><div className="eyebrow">SWISS EPHEMERIS · TROPICAL · GEOCENTRIC</div><h2>Find exact aspect formations</h2><p>Positions are root-refined from apparent ecliptic longitudes. Calculations are astronomical data, not market predictions.</p></div></section>

        {error && <Alert type="error" showIcon message="Calculation could not be completed" description={error} className="api-alert" />}

        <section className="calculator-layout">
          <Card bordered={false} className="calculator-form">
            <div className="eyebrow">CALCULATION INPUTS</div>
            <h3>Choose planets, aspects and dates</h3>
            <div className="form-label">Planetary pair</div>
            <div className="pair-fields">
              <Select value={planet1} options={PLANETS.map((planet) => ({ value: planet, label: planet }))} onChange={setPlanet1} />
              <span>×</span>
              <Select value={planet2} options={PLANETS.filter((planet) => planet !== planet1).map((planet) => ({ value: planet, label: planet }))} onChange={setPlanet2} />
            </div>
            <div className="form-label">Date range</div>
            <div className="date-fields"><label>From<input type="date" value={startDate} max={endDate} onChange={(event) => setStartDate(event.target.value)} /></label><label>Through<input type="date" value={endDate} min={startDate} onChange={(event) => setEndDate(event.target.value)} /></label></div>
            <div className="form-label">Aspects</div>
            <Checkbox.Group value={aspects} onChange={(values) => setAspects(values as string[])} className="aspect-checkboxes">
              {ASPECT_OPTIONS.map((aspect) => <Checkbox key={aspect.name} value={aspect.name}>{aspect.name} <small>{aspect.angle}°</small></Checkbox>)}
            </Checkbox.Group>
            <div className="settings-note"><span>◉</span> Apparent geocentric longitude · Swiss Ephemeris data files · UTC root solving</div>
            <Button type="primary" size="large" onClick={calculate} loading={calculating} disabled={aspects.length === 0 || planet1 === planet2} block>Calculate exact events</Button>
          </Card>

          <Card bordered={false} className="calculator-results">
            <div className="results-heading"><div><div className="eyebrow">CALCULATED EVENTS</div><h3>{selectedPair.replace("|", " × ")}</h3></div>{run && <Tag color={run.status === "completed" ? "green" : run.status === "failed" ? "red" : "blue"}>{run.status}</Tag>}</div>
            {calculating ? <div className="calc-loading"><Spin /><span>Searching dates and refining exact timestamps…</span></div> : events.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={run?.status === "completed" ? "No matching aspect events in this date range" : "Choose a date range and calculate to see exact events"} /> : (
              <div className="result-table-wrap"><table className="result-table"><thead><tr><th>Exact time (IST)</th><th>Aspect</th><th>Separation</th></tr></thead><tbody>
                {events.map((event) => <tr key={event.id} className={selected?.id === event.id ? "selected" : ""} onClick={() => setSelected(event)}><td>{formatLocal(event.exact_time_local)}</td><td>{event.aspect_name} · {event.aspect_angle_degrees}°</td><td>{event.angular_separation_degrees.toFixed(5)}°</td></tr>)}
              </tbody></table></div>
            )}
          </Card>
        </section>

        <section className="details-grid">
          <Card bordered={false} className="event-inspector">
            <div className="eyebrow">EVENT DETAILS</div>
            {!selected ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Select a calculated event to inspect its positions and orb" /> : <>
              <h3>{selected.planet_1} <span>×</span> {selected.planet_2} <Tag>{selected.aspect_name} {selected.aspect_angle_degrees}°</Tag></h3>
              <div className="inspector-time">{formatLocal(selected.exact_time_local)}</div>
              <div className="event-facts"><span>Longitude {selected.planet_1}<b>{selected.longitude_1_degrees.toFixed(6)}°</b></span><span>Longitude {selected.planet_2}<b>{selected.longitude_2_degrees.toFixed(6)}°</b></span><span>Angular separation<b>{selected.angular_separation_degrees.toFixed(6)}°</b></span></div>
              <div className="orb-row"><span>Orb 15 minutes before <b>{selected.orb_before_degrees?.toFixed(6) ?? "—"}°</b></span><span>Orb 15 minutes after <b>{selected.orb_after_degrees?.toFixed(6) ?? "—"}°</b></span></div>
              <details className="settings-details"><summary>Calculation settings</summary><pre>{JSON.stringify(selected.calculation_settings, null, 2)}</pre></details>
            </>}
          </Card>
          <div className="linked-records">
            <Card bordered={false}><div className="eyebrow">TRADER SOURCE</div><h3>Related predictions</h3><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No trader source record linked to this event" /></Card>
            <Card bordered={false}><div className="eyebrow">OBSERVED MARKET DATA</div><h3>Historical price behaviour</h3><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Import OHLC candles to view observed behaviour" /></Card>
          </div>
        </section>
      </main>
    </div>
  );
}

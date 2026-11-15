"use client";

import Link from "next/link";
import { Alert, Button, Card, Select, message } from "antd";
import { useState } from "react";

const API_ROOT = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const YEARS = Array.from({ length: 15 }, (_, index) => 2026 + index);

export default function ReportsPage() {
  const [year, setYear] = useState(2026);
  const [reportDate, setReportDate] = useState("2026-01-01");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function download() {
    setBusy(true); setError("");
    try {
      const response = await fetch(`${API_ROOT}/api/reports/calendar/${year}.pdf`, { cache: "no-store" });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `Report request failed (${response.status})`);
      }
      const blob = await response.blob();
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = href; anchor.download = `astro-market-calendar-${year}.pdf`; anchor.click();
      URL.revokeObjectURL(href);
      message.success("Annual calendar downloaded");
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : "Could not download the report";
      setError(detail); message.error(detail);
    } finally { setBusy(false); }
  }
  async function downloadDaily() {
    setBusy(true); setError("");
    try {
      const response = await fetch(`${API_ROOT}/api/reports/daily/${reportDate}.pdf`, { cache: "no-store" });
      if (!response.ok) { const body = await response.json().catch(() => null); throw new Error(body?.detail ?? `Report request failed (${response.status})`); }
      const href = URL.createObjectURL(await response.blob()); const anchor = document.createElement("a");
      anchor.href = href; anchor.download = `astro-market-daily-${reportDate}.pdf`; anchor.click(); URL.revokeObjectURL(href);
      message.success("Daily research report downloaded");
    } catch (reason) { const detail = reason instanceof Error ? reason.message : "Could not download the report"; setError(detail); message.error(detail); }
    finally { setBusy(false); }
  }
  return <div className="app-shell">
    <aside className="sidebar"><div className="brand-mark">✦</div><div className="brand-copy"><strong>ASTRO</strong><span>MARKET ANALYZER</span></div>
      <div className="nav-label">WORKSPACE</div><Link href="/" className="nav-item"><span className="nav-glyph">⌂</span>Dashboard</Link><Link href="/calendar" className="nav-item"><span className="nav-glyph">▦</span>Astro Calendar</Link><Link href="/calculator" className="nav-item"><span className="nav-glyph">◈</span>Planetary Calculator</Link><Link href="/timing" className="nav-item"><span className="nav-glyph">⌁</span>Intraday Analyzer</Link><Link href="/backtest" className="nav-item"><span className="nav-glyph">▤</span>Market Backtesting</Link><Link href="/rules" className="nav-item"><span className="nav-glyph">◇</span>Trader Rulebook</Link><div className="nav-label later-label">ANALYSIS</div><Link href="/reports" className="nav-item active"><span className="nav-glyph">↗</span>PDF Reports</Link><div className="sidebar-footer"><span className="status-dot" /> Local research workspace</div>
    </aside>
    <main className="main-content">
      <header className="topbar"><div><div className="crumb">ANALYSIS <span>/</span> PDF REPORTS</div><h1>PDF Reports</h1></div><span className="timezone-chip">◷ &nbsp; Local research</span></header>
      <section className="intro-row"><div><div className="eyebrow">PRINTABLE REFERENCE</div><h2>Annual Astro Calendar</h2><p>A month per page with exact calculated planetary aspects and local event times.</p></div></section>
      {error && <Alert type="warning" showIcon message="Report unavailable" description={error} />}
      <Card className="report-card" bordered={false}><div className="report-controls"><label>Calendar year<Select value={year} onChange={setYear} options={YEARS.map(value => ({ value, label: String(value) }))} /></label><Button type="primary" loading={busy} onClick={download}>Download annual PDF</Button></div><p>Calculate the selected year on the calendar page first. The PDF is generated locally from its saved event run.</p><div className="report-controls"><label>Daily research date<input type="date" value={reportDate} onChange={(event) => setReportDate(event.target.value)} /></label><Button loading={busy} onClick={downloadDaily}>Download daily report</Button></div><p>The daily report includes calculated events, matching source notes and associated rulebook hypotheses already recorded in the workspace.</p><Link href="/calendar">Open Astro Calendar →</Link><div className="report-note">Astronomical event timings are reference data. Reports do not invent predictions or make market direction claims.</div></Card>
    </main>
  </div>;
}

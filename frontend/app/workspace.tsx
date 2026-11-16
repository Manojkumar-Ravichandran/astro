"use client";

import {
  Alert,
  Badge,
  Button,
  Card,
  ColorPicker,
  Divider,
  Empty,
  Modal,
  Select,
  Skeleton,
  Space,
  Statistic,
  Tag,
  Tooltip,
  message,
} from "antd";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

const API_ROOT = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ASPECTS = [
  { name: "Conjunction", angle: 0, color: "#b7791f" },
  { name: "Semi-square", angle: 45, color: "#c05670" },
  { name: "Sextile", angle: 60, color: "#27836b" },
  { name: "Square", angle: 90, color: "#d24b48" },
  { name: "Trine", angle: 120, color: "#3980be" },
  { name: "Sesquiquadrate", angle: 135, color: "#8756a3" },
  { name: "Opposition", angle: 180, color: "#5b6474" },
];
const PAIRS = [
  "Sun|Moon", "Moon|Mercury", "Moon|Venus", "Moon|Mars", "Moon|Jupiter", "Moon|Saturn",
  "Sun|Mercury", "Sun|Venus", "Sun|Mars", "Sun|Jupiter", "Sun|Saturn", "Venus|Mars",
  "Venus|Jupiter", "Venus|Saturn", "Mars|Jupiter", "Mars|Saturn", "Jupiter|Saturn",
];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const CALENDAR_WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const YEARS = Array.from({ length: 15 }, (_, index) => 2026 + index);
const DEFAULT_COLORS = Object.fromEntries(ASPECTS.map((aspect) => [aspect.name, aspect.color]));

type AspectName = (typeof ASPECTS)[number]["name"];
type AstroEvent = {
  id: number;
  planet_1: string;
  planet_2: string;
  aspect_name: AspectName;
  aspect_angle_degrees: number;
  exact_time_utc: string;
  exact_time_local: string;
  timezone: string;
  longitude_1_degrees: number;
  longitude_2_degrees: number;
  angular_separation_degrees: number;
};
type Run = {
  id: number;
  year: number;
  status: "running" | "completed" | "failed";
  started_at: string;
  completed_at?: string | null;
  event_count: number;
  error_message?: string | null;
};
type Dashboard = {
  year: number;
  run: Run | null;
  total_events: number;
  important_dates: number;
  moon_events: number;
  upcoming_events: Array<{
    id: number;
    planet_1: string;
    planet_2: string;
    aspect_name: string;
    aspect_angle_degrees: number;
    exact_time_local: string;
  }>;
  aspect_counts: Array<{ aspect_name: string; total: number }>;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `API request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function localDate(iso: string) {
  return iso.slice(0, 10);
}

function clockTime(iso: string) {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(iso));
}

function longDate(iso: string) {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata", day: "numeric", month: "long", year: "numeric",
  }).format(new Date(iso));
}

function downloadEventReport(eventId: number) {
  const anchor = document.createElement("a");
  anchor.href = `${API_ROOT}/api/reports/event/${eventId}.pdf`;
  anchor.download = `astro-market-event-${eventId}.pdf`;
  anchor.click();
}

function monthName(year: number, month: number) {
  return new Intl.DateTimeFormat("en", { month: "long", year: "numeric" }).format(new Date(year, month, 1));
}

function MonthGrid({ year, month, events, colors, onSelect }: {
  year: number;
  month: number;
  events: AstroEvent[];
  colors: Record<string, string>;
  onSelect: (day: string) => void;
}) {
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const startOffset = (new Date(year, month, 1).getDay() + 6) % 7;
  const cells = Array.from({ length: startOffset + daysInMonth }, (_, index) => index < startOffset ? null : index - startOffset + 1);
  return <Card className="month-card" bordered={false}>
    <h3>{monthName(year, month)}</h3>
    <div className="month-grid">{WEEKDAYS.map((day) => <span key={day} className="weekday">{day}</span>)}
      {cells.map((day, index) => {
        if (day === null) return <span className="day-blank" key={`blank-${index}`} />;
        const dayKey = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        const dayEvents = events.filter((event) => localDate(event.exact_time_local) === dayKey);
        return <Tooltip key={dayKey} title={dayEvents.length ? `${dayEvents.length} planetary event${dayEvents.length === 1 ? "" : "s"}` : undefined}>
          <button type="button" className={`day-cell ${dayEvents.length ? "has-events" : ""}`} onClick={() => onSelect(dayKey)} aria-label={`${dayKey}${dayEvents.length ? `, ${dayEvents.length} events` : ""}`}>
            <span>{day}</span>{dayEvents.length > 0 && <span className="event-dots" aria-hidden="true">{dayEvents.slice(0, 4).map((event) => <i key={event.id} style={{ background: colors[event.aspect_name] ?? "#697586" }} />)}{dayEvents.length > 4 && <small>+{dayEvents.length - 4}</small>}</span>}
          </button>
        </Tooltip>;
      })}
    </div>
  </Card>;
}

function FullCalendarGrid({
  date, view, events, colors, onSelect,
}: {
  date: Date;
  view: "month" | "week" | "list";
  events: AstroEvent[];
  colors: Record<string, string>;
  onSelect: (day: string) => void;
}) {
  const month = date.getMonth();
  const year = date.getFullYear();
  const firstDay = new Date(year, month, 1);
  const gridStart = new Date(year, month, 1 - firstDay.getDay());
  const weekStart = new Date(date.getFullYear(), date.getMonth(), date.getDate() - date.getDay());
  const now = new Date();
  const todayKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const days = view === "week" ? 7 : 42;
  const cells = Array.from({ length: days }, (_, index) => new Date(
    view === "week" ? weekStart.getFullYear() : gridStart.getFullYear(),
    view === "week" ? weekStart.getMonth() : gridStart.getMonth(),
    (view === "week" ? weekStart.getDate() : gridStart.getDate()) + index,
  ));
  const listEvents = events.filter((event) => localDate(event.exact_time_local).startsWith(`${year}-${String(month + 1).padStart(2, "0")}`));
  return (
    <div className={`full-calendar-grid ${view === "week" ? "calendar-week-view" : ""}`}>
      {view !== "list" && <>
        <div className="full-calendar-weekdays">{CALENDAR_WEEKDAYS.map((day) => <div key={day}>{day}</div>)}</div>
        <div className="full-calendar-days">{cells.map((day) => {
          const dayKey = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
          const dayEvents = events.filter((event) => localDate(event.exact_time_local) === dayKey);
          const shown = view === "week" ? dayEvents : dayEvents.slice(0, 3);
          return <div key={dayKey} className={`full-calendar-day ${view === "month" && day.getMonth() !== month ? "calendar-outside" : ""}`}>
            <button className={`calendar-day-number ${dayKey === todayKey ? "calendar-today" : ""}`} onClick={() => onSelect(dayKey)}>{day.getDate()}</button>
            <div className="calendar-day-events">{shown.map((event) => <Tooltip key={event.id} title={`${event.aspect_name} · ${event.aspect_angle_degrees}°`}>
              <button className="calendar-event-chip" onClick={() => onSelect(dayKey)} style={{ "--event-color": colors[event.aspect_name] ?? "#697586" } as React.CSSProperties}>
                <i />{clockTime(event.exact_time_local)} {event.planet_1} × {event.planet_2}
              </button>
            </Tooltip>)}{dayEvents.length > shown.length && <button className="calendar-more-events" onClick={() => onSelect(dayKey)}>+{dayEvents.length - shown.length} more</button>}</div>
          </div>;
        })}</div>
      </>}
      {view === "list" && <div className="calendar-list-view">{listEvents.map((event) => <button key={event.id} className="calendar-list-event" onClick={() => onSelect(localDate(event.exact_time_local))}><span>{longDate(event.exact_time_local)}</span><i style={{ background: colors[event.aspect_name] ?? "#697586" }} /><strong>{event.planet_1} × {event.planet_2}</strong><span>{event.aspect_name} · {event.aspect_angle_degrees}°</span><time>{clockTime(event.exact_time_local)} IST</time></button>)}</div>}
    </div>
  );
}

export default function Workspace({ view }: { view: "dashboard" | "calendar" | "calculator" }) {
  const [year, setYear] = useState(2026);
  const [calendarDate, setCalendarDate] = useState(() => new Date(2026, new Date().getMonth(), 1));
  const [calendarView, setCalendarView] = useState<"month" | "week" | "list">("month");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [events, setEvents] = useState<AstroEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [starting, setStarting] = useState(false);
  const [planetFilter, setPlanetFilter] = useState<string | undefined>();
  const [pairFilter, setPairFilter] = useState<string | undefined>();
  const [aspectFilter, setAspectFilter] = useState<string | undefined>();
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [colors, setColors] = useState<Record<string, string>>(DEFAULT_COLORS);
  const [messageApi, contextHolder] = message.useMessage();

  useEffect(() => {
    const stored = window.localStorage.getItem("astro-aspect-colors");
    if (stored) {
      try { setColors({ ...DEFAULT_COLORS, ...JSON.parse(stored) as Record<string, string> }); }
      catch { window.localStorage.removeItem("astro-aspect-colors"); }
    }
  }, []);

  const loadData = useCallback(async (selectedYear: number, showLoading = false) => {
    if (showLoading) setLoading(true);
    try {
      const [summary, nextEvents] = await Promise.all([
        api<Dashboard>(`/api/dashboard?year=${selectedYear}`),
        api<AstroEvent[]>(`/api/events?year=${selectedYear}`),
      ]);
      setDashboard(summary);
      setEvents(nextEvents);
      setRun(summary.run);
      setApiError(null);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Could not reach the local API");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadData(year, true); }, [year, loadData]);

  useEffect(() => {
    if (run?.status !== "running") return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await api<Run | null>(`/api/calculations/latest?year=${year}`);
        if (!latest || latest.status === "running") return;
        setRun(latest);
        await loadData(year);
        if (latest.status === "completed") messageApi.success(`Calculated ${latest.event_count.toLocaleString()} events for ${year}`);
        else messageApi.error(latest.error_message ?? "The calculation failed");
      } catch (error) {
        setApiError(error instanceof Error ? error.message : "Calculation status could not be loaded");
      }
    }, 1800);
    return () => window.clearInterval(timer);
  }, [run?.status, year, loadData, messageApi]);

  const filteredEvents = useMemo(() => events.filter((event) => {
    const pair = `${event.planet_1}|${event.planet_2}`;
    return (!planetFilter || event.planet_1 === planetFilter || event.planet_2 === planetFilter)
      && (!pairFilter || pair === pairFilter)
      && (!aspectFilter || event.aspect_name === aspectFilter);
  }), [events, planetFilter, pairFilter, aspectFilter]);

  const selectedEvents = selectedDate
    ? filteredEvents.filter((event) => localDate(event.exact_time_local) === selectedDate)
    : [];

  async function startCalculation() {
    setStarting(true);
    try {
      const created = await api<Run>("/api/calculations", {
        method: "POST", body: JSON.stringify({ year }),
      });
      setRun(created);
      messageApi.info(`Calculation queued for ${year}`);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "Could not start calculation");
    } finally {
      setStarting(false);
    }
  }

  function saveColors(next: Record<string, string>) {
    setColors(next);
    window.localStorage.setItem("astro-aspect-colors", JSON.stringify(next));
  }

  const runStatus = run?.status === "running" ? "Calculating" : run?.status === "completed" ? "Ready" : run?.status === "failed" ? "Failed" : "Not calculated";
  const isDashboard = view === "dashboard";

  return (
    <div className="app-shell">
      {contextHolder}
      <aside className="sidebar">
        <div className="brand-mark">✳</div>
        <div className="brand-copy"><strong>ASTRO</strong><span>MARKET ANALYZER</span></div>
        <div className="nav-label">RESEARCH</div>
        <Link href="/" className={`nav-item ${isDashboard ? "active" : ""}`}><span className="nav-glyph">▦</span>Dashboard</Link>
        <Link href="/calendar" className={`nav-item ${view === "calendar" ? "active" : ""}`}><span className="nav-glyph">◷</span>Astro Calendar</Link>
        <Link href="/calculator" className={`nav-item ${view === "calculator" ? "active" : ""}`}><span className="nav-glyph">◈</span>Planetary Calculator</Link>
        <Link href="/timing" className="nav-item"><span className="nav-glyph">⌁</span>Intraday Analyzer</Link>
        <Link href="/backtest" className="nav-item"><span className="nav-glyph">▤</span>Market Backtesting</Link>
        <Link href="/rules" className="nav-item"><span className="nav-glyph">◇</span>Trader Rulebook</Link>
        <div className="nav-label later-label">ANALYSIS</div>
        <Link href="/reports" className="nav-item"><span className="nav-glyph">↗</span>PDF Reports</Link>
        <div className="sidebar-footer"><span className="status-dot" /> Local research workspace</div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div><div className="crumb">RESEARCH <span>/</span> {isDashboard ? "OVERVIEW" : "YEARLY CALENDAR"}</div><h1>{isDashboard ? "Dashboard" : "Astro Calendar"}</h1></div>
          <div className="top-actions">
            <span className="timezone-chip">◷ &nbsp; Asia / Kolkata</span>
            <Select aria-label="Calendar year" value={year} options={YEARS.map((value) => ({ value, label: String(value) }))} onChange={(value) => { setYear(value); setCalendarDate((current) => new Date(value, current.getMonth(), current.getDate())); }} />
            <Button type="primary" onClick={startCalculation} loading={starting || run?.status === "running"}>Calculate year</Button>
          </div>
        </header>

        {apiError && <Alert className="api-alert" type="error" showIcon message="Local API unavailable" description={`${apiError}. Start the FastAPI service to load and calculate events.`} />}

        {isDashboard && <section className="intro-row">
          <div><div className="eyebrow">ASTRONOMY RESEARCH · {year}</div><h2>{isDashboard ? "Year at a glance" : "Planetary aspect calendar"}</h2><p>Planetary events are calculated independently; trader interpretations and market outcomes remain separate.</p></div>
          <div className={`run-pill ${run?.status ?? "empty"}`}><span className="status-dot" />{runStatus}{run?.status === "completed" && <span className="run-count">{run.event_count.toLocaleString()} events</span>}</div>
        </section>}

        {isDashboard && <section className="stats-grid">
          <Card className="stat-card" bordered={false}><div className="stat-label">PLANETARY EVENTS</div>{loading ? <Skeleton active paragraph={false} /> : <Statistic value={dashboard?.total_events ?? 0} valueStyle={{ fontSize: 28, fontWeight: 650 }} />}<div className="stat-foot">Exact aspect formations</div></Card>
          <Card className="stat-card" bordered={false}><div className="stat-label">IMPORTANT DATES</div>{loading ? <Skeleton active paragraph={false} /> : <Statistic value={dashboard?.important_dates ?? 0} valueStyle={{ fontSize: 28, fontWeight: 650 }} />}<div className="stat-foot">Days with one or more aspects</div></Card>
          <Card className="stat-card" bordered={false}><div className="stat-label">MOON-RELATED</div>{loading ? <Skeleton active paragraph={false} /> : <Statistic value={dashboard?.moon_events ?? 0} valueStyle={{ fontSize: 28, fontWeight: 650 }} />}<div className="stat-foot">Events involving the Moon</div></Card>
          <Card className="stat-card status-stat" bordered={false}><div className="stat-label">CALCULATION STATUS</div><div className="status-value"><Badge status={run?.status === "completed" ? "success" : run?.status === "running" ? "processing" : run?.status === "failed" ? "error" : "default"} />{runStatus}</div><div className="stat-foot">Swiss Ephemeris · Tropical</div></Card>
        </section>}

        {isDashboard ? <section className="section-heading">
          <div><div className="eyebrow">{isDashboard ? "CALENDAR OVERVIEW" : "JANUARY — DECEMBER"}</div><h2>{isDashboard ? "Event calendar" : "Planetary aspect calendar"}</h2></div>
          <Space wrap>
            <Select allowClear placeholder="All planets" value={planetFilter} onChange={setPlanetFilter} options={["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"].map((p) => ({ value: p, label: p }))} />
            <Select allowClear placeholder="All planetary pairs" value={pairFilter} onChange={setPairFilter} options={PAIRS.map((pair) => ({ value: pair, label: pair.replace("|", " × ") }))} />
            <Select allowClear placeholder="All aspects" value={aspectFilter} onChange={setAspectFilter} options={ASPECTS.map((a) => ({ value: a.name, label: `${a.name} · ${a.angle}°` }))} />
            <Button onClick={() => setPaletteOpen(true)}>Marker colors</Button>
          </Space>
        </section> : <section className="full-calendar-toolbar">
          <div className="full-calendar-period-controls">
            <Button onClick={() => { const now = new Date(); setYear(now.getFullYear()); setCalendarDate(new Date(now.getFullYear(), now.getMonth(), now.getDate())); }}>Today</Button>
            <Button aria-label="Previous period" onClick={() => setCalendarDate((current) => calendarView === "month" ? new Date(current.getFullYear(), current.getMonth() - 1, 1) : new Date(current.getFullYear(), current.getMonth(), current.getDate() - 7))}>‹</Button>
            <Button aria-label="Next period" onClick={() => setCalendarDate((current) => calendarView === "month" ? new Date(current.getFullYear(), current.getMonth() + 1, 1) : new Date(current.getFullYear(), current.getMonth(), current.getDate() + 7))}>›</Button>
            <h2>{monthName(calendarDate.getFullYear(), calendarDate.getMonth())}</h2>
          </div>
          <div className="full-calendar-view-controls">{(["week", "month", "list"] as const).map((item) => <Button key={item} type={calendarView === item ? "primary" : "text"} onClick={() => setCalendarView(item)}>{item[0].toUpperCase() + item.slice(1)}</Button>)}</div>
          <Space wrap className="full-calendar-filters">
            <Select allowClear placeholder="All planets" value={planetFilter} onChange={setPlanetFilter} options={["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"].map((planet) => ({ value: planet, label: planet }))} />
            <Select allowClear placeholder="All planetary pairs" value={pairFilter} onChange={setPairFilter} options={PAIRS.map((pair) => ({ value: pair, label: pair.replace("|", " × ") }))} />
            <Select allowClear placeholder="All aspects" value={aspectFilter} onChange={setAspectFilter} options={ASPECTS.map((aspect) => ({ value: aspect.name, label: `${aspect.name} · ${aspect.angle}°` }))} />
            <Button onClick={() => setPaletteOpen(true)}>Marker colors</Button>
          </Space>
        </section>}

        <div className="aspect-legend">
          {ASPECTS.map((aspect) => <span key={aspect.name}><i style={{ background: colors[aspect.name] }} />{aspect.name}<small>{aspect.angle}°</small></span>)}
        </div>

        {loading && !events.length ? (
          <div className="calendar-loading"><Skeleton active /><Skeleton active /><Skeleton active /></div>
        ) : filteredEvents.length === 0 ? (
          <Card className="empty-calendar" bordered={false}>
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<span>{run?.status === "completed" ? "No events match these filters" : `No calculated events for ${year} yet`}</span>} />
            <Button type="primary" onClick={startCalculation} loading={starting || run?.status === "running"}>{run?.status === "completed" ? "Recalculate year" : "Calculate planetary events"}</Button>
          </Card>
        ) : (
          isDashboard ? <div className="months-grid">
            {Array.from({ length: 12 }, (_, month) => <MonthGrid key={`${year}-${month}`} year={year} month={month} events={filteredEvents} colors={colors} onSelect={setSelectedDate} />)}
          </div> : <FullCalendarGrid date={calendarDate} view={calendarView} events={filteredEvents} colors={colors} onSelect={setSelectedDate} />
        )}

        {isDashboard && <section className="bottom-grid">
          <Card className="bottom-card" bordered={false}>
            <div className="bottom-title"><div><div className="eyebrow">NEXT FORMATIONS</div><h3>Upcoming aspects</h3></div><span className="subtle-count">{dashboard?.upcoming_events.length ?? 0} listed</span></div>
            {!dashboard?.upcoming_events.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Upcoming events appear after calculation" /> : dashboard.upcoming_events.slice(0, 5).map((event) => (
              <div className="upcoming-row" key={event.id}>
                <span className="upcoming-date">{longDate(event.exact_time_local)}</span>
                <span className="upcoming-pair">{event.planet_1} <b>×</b> {event.planet_2}</span>
                <Tag color={colors[event.aspect_name]}>{event.aspect_name} {event.aspect_angle_degrees}°</Tag>
                <span className="upcoming-time">{clockTime(event.exact_time_local)}</span>
              </div>
            ))}
          </Card>
          <Card className="bottom-card aspect-summary" bordered={false}>
            <div className="eyebrow">EVENT MIX</div><h3>Aspect summary</h3>
            {!dashboard?.aspect_counts.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No calculated events" /> : dashboard.aspect_counts.map((item) => (
              <div className="mix-row" key={item.aspect_name}>
                <span className="mix-dot" style={{ background: colors[item.aspect_name] }} />
                <span>{item.aspect_name}</span><strong>{item.total}</strong>
                <div className="mix-track"><i style={{ width: `${Math.max(5, (item.total / dashboard.total_events) * 100)}%`, background: colors[item.aspect_name] }} /></div>
              </div>
            ))}
          </Card>
        </section>}

        {isDashboard && <footer className="page-footer"><span>ASTRO MARKET ANALYZER</span><span>Research hypotheses only · No predictive claims</span><span>Swiss Ephemeris · {year}</span></footer>}
      </main>

      <Modal open={Boolean(selectedDate)} title={selectedDate ? new Intl.DateTimeFormat("en", { dateStyle: "full", timeZone: "UTC" }).format(new Date(`${selectedDate}T12:00:00Z`)) : "Date details"} onCancel={() => setSelectedDate(null)} footer={<Button onClick={() => setSelectedDate(null)}>Close</Button>} width={620}>
        {selectedEvents.length === 0 ? <Empty description="No planetary events on this date for the active filters" /> : <div className="event-list">
          {selectedEvents.map((event) => (
            <div className="event-detail" key={event.id}>
              <div className="event-detail-head"><div><div className="eyebrow">EXACT ASTRONOMICAL EVENT</div><strong>{event.planet_1} <span>×</span> {event.planet_2}</strong></div><Space><Tag color={colors[event.aspect_name]}>{event.aspect_name} · {event.aspect_angle_degrees}°</Tag><Button size="small" onClick={() => downloadEventReport(event.id)}>Event PDF</Button></Space></div>
              <div className="event-time">{clockTime(event.exact_time_local)} <small>IST</small></div>
              <Divider />
              <div className="event-facts"><span>Longitude {event.planet_1}<b>{event.longitude_1_degrees.toFixed(5)}°</b></span><span>Longitude {event.planet_2}<b>{event.longitude_2_degrees.toFixed(5)}°</b></span><span>Angular separation<b>{event.angular_separation_degrees.toFixed(5)}°</b></span></div>
            </div>
          ))}
        </div>}
      </Modal>

      <Modal open={paletteOpen} title="Calendar marker colors" onCancel={() => setPaletteOpen(false)} onOk={() => setPaletteOpen(false)} okText="Done">
        <p className="palette-hint">Choose a color for each standard aspect marker. Your settings are saved in this browser.</p>
        <div className="palette-list">{ASPECTS.map((aspect) => <div className="palette-row" key={aspect.name}><span>{aspect.name}<small>{aspect.angle}°</small></span><ColorPicker value={colors[aspect.name]} onChange={(color) => saveColors({ ...colors, [aspect.name]: color.toHexString() })} showText /></div>)}</div>
        <Button className="reset-colors" onClick={() => saveColors(DEFAULT_COLORS)}>Reset to defaults</Button>
      </Modal>
    </div>
  );
}

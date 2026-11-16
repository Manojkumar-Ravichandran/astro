"use client";

import dynamic from "next/dynamic";
import "./calendar-layout.module.css";

const CalendarWorkspace = dynamic(() => import("../workspace"), {
  ssr: false,
  loading: () => <main className="calendar-route-loading">Loading Astro Calendar…</main>,
});

export default function CalendarClient() {
  return <CalendarWorkspace view="calendar" />;
}

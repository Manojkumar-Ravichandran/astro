"use client";

import Link from "next/link";
import { Alert, Button, Card, Empty, Input, Modal, Select, Spin, Tag, message } from "antd";
import TextArea from "antd/es/input/TextArea";
import { useEffect, useState } from "react";

const API_ROOT = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const PLANETS = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"];
const ASPECTS = [
  { name: "Conjunction", angle: 0 }, { name: "Semi-square", angle: 45 },
  { name: "Sextile", angle: 60 }, { name: "Square", angle: 90 },
  { name: "Trine", angle: 120 }, { name: "Sesquiquadrate", angle: 135 },
  { name: "Opposition", angle: 180 },
];
const STATUSES = ["hypothesis", "under_test", "supported", "not_supported", "retired"];
type RuleAspect = { planet_1: string; planet_2: string; aspect_angle_degrees: number };
type Rule = {
  id: number;
  title: string;
  hypothesis_text: string;
  status: string;
  source_document_id: number | null;
  source_title: string | null;
  aspects: RuleAspect[];
  created_at: string;
  updated_at: string;
};
type EditorState = { id?: number; title: string; text: string; status: string; sourceId: number | null; aspects: RuleAspect[] };

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

function aspectName(angle: number) {
  return ASPECTS.find((aspect) => aspect.angle === angle)?.name ?? `${angle}°`;
}

function statusLabel(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function emptyEditor(): EditorState {
  return { title: "", text: "", status: "hypothesis", sourceId: null, aspects: [{ planet_1: "Moon", planet_2: "Venus", aspect_angle_degrees: 90 }] };
}

export default function TraderRulebookPage() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [includeRetired, setIncludeRetired] = useState(false);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [messageApi, contextHolder] = message.useMessage();

  async function loadRules(include = includeRetired) {
    const loaded = await api<Rule[]>(`/api/rules?include_retired=${include}`);
    setRules(loaded);
  }

  useEffect(() => {
    void loadRules().catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Could not load rules"))
      .finally(() => setLoading(false));
  }, []);

  function editRule(rule?: Rule) {
    if (!rule) { setEditor(emptyEditor()); return; }
    setEditor({
      id: rule.id,
      title: rule.title,
      text: rule.hypothesis_text,
      status: rule.status,
      sourceId: rule.source_document_id,
      aspects: rule.aspects.map((aspect) => ({ ...aspect })),
    });
  }

  function changeAspect(index: number, field: keyof RuleAspect, value: string | number) {
    if (!editor) return;
    setEditor({ ...editor, aspects: editor.aspects.map((aspect, current) => current === index ? { ...aspect, [field]: value } : aspect) });
  }

  async function saveRule() {
    if (!editor || !editor.title.trim() || !editor.text.trim() || editor.aspects.length === 0) return;
    setSaving(true);
    try {
      const body = {
        title: editor.title,
        hypothesis_text: editor.text,
        status: editor.status,
        source_document_id: editor.sourceId,
        aspects: editor.aspects,
      };
      if (editor.id) await api<Rule>(`/api/rules/${editor.id}`, { method: "PATCH", body: JSON.stringify(body) });
      else await api<Rule>("/api/rules", { method: "POST", body: JSON.stringify(body) });
      setEditor(null);
      await loadRules();
      messageApi.success(editor.id ? "Hypothesis updated" : "Hypothesis saved");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not save the hypothesis");
    } finally {
      setSaving(false);
    }
  }

  async function setStatus(rule: Rule, status: string) {
    try {
      await api<Rule>(`/api/rules/${rule.id}`, { method: "PATCH", body: JSON.stringify({ status }) });
      await loadRules();
      messageApi.success(`Status changed to ${statusLabel(status)}`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not update status");
    }
  }

  async function retire(rule: Rule) {
    try {
      await api<{ id: number; status: string }>(`/api/rules/${rule.id}`, { method: "DELETE" });
      await loadRules();
      messageApi.success("Rule retired and kept in the research history");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not retire the rule");
    }
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
        <Link href="/timing" className="nav-item"><span className="nav-glyph">⌁</span>Intraday Analyzer</Link>
        <Link href="/backtest" className="nav-item"><span className="nav-glyph">▤</span>Market Backtesting</Link>
        <Link href="/rules" className="nav-item active"><span className="nav-glyph">◇</span>Trader Rulebook</Link>
        <div className="nav-label later-label">REPORTS</div><Link href="/reports" className="nav-item"><span className="nav-glyph">↗</span>PDF Reports</Link>
        <div className="sidebar-footer"><span className="status-dot" /> Local research workspace</div>
      </aside>

      <main className="main-content">
        <header className="topbar"><div><div className="crumb">RESEARCH <span>/</span> HYPOTHESES</div><h1>Trader Rulebook</h1></div><Button type="primary" onClick={() => editRule()}>Add hypothesis</Button></header>
        <section className="intro-row"><div><div className="eyebrow">SOURCE MATERIAL · TESTABLE CLAIMS</div><h2>Trader-provided rules</h2><p>These notes are hypotheses from the source material. Status describes research progress, not proof of market behaviour.</p></div></section>
        {error && <Alert className="api-alert" type="error" showIcon message="Rulebook update issue" description={error} />}
        <div className="rule-toolbar"><span>{rules.length} rule{rules.length === 1 ? "" : "s"} shown</span><label><input type="checkbox" checked={includeRetired} onChange={async (event) => { setIncludeRetired(event.target.checked); await loadRules(event.target.checked); }} /> Include retired</label></div>

        {loading ? <Card bordered={false}><Spin /></Card> : rules.length === 0 ? <Card bordered={false} className="empty-calendar"><Empty description="No hypotheses yet" /><Button type="primary" onClick={() => editRule()}>Add a hypothesis</Button></Card> : <section className="rules-grid">{rules.map((rule) => (
          <Card key={rule.id} bordered={false} className={`rule-card ${rule.status === "retired" ? "retired" : ""}`}>
            <div className="rule-card-top"><Tag color={rule.status === "supported" ? "green" : rule.status === "not_supported" ? "red" : rule.status === "under_test" ? "blue" : rule.status === "retired" ? "default" : "gold"}>{statusLabel(rule.status)}</Tag><span className="rule-source">{rule.source_title ?? "No source linked"}</span></div>
            <h3>{rule.title}</h3>
            <p className="rule-hypothesis">{rule.hypothesis_text}</p>
            <div className="rule-aspect-list">{rule.aspects.map((aspect, index) => <Tag key={`${aspect.planet_1}-${aspect.planet_2}-${index}`}>{aspect.planet_1} × {aspect.planet_2} · {aspectName(aspect.aspect_angle_degrees)} {aspect.aspect_angle_degrees}°</Tag>)}</div>
            <div className="rule-card-footer"><Select size="small" value={rule.status} onChange={(status) => void setStatus(rule, status)} options={STATUSES.map((status) => ({ value: status, label: statusLabel(status) }))} /><div><Button size="small" onClick={() => editRule(rule)}>Edit</Button>{rule.status !== "retired" && <Button size="small" danger onClick={() => Modal.confirm({ title: "Retire this hypothesis?", content: "It will remain in the research history with its source association.", okText: "Retire", okButtonProps: { danger: true }, onOk: () => retire(rule) })}>Retire</Button>}</div></div>
          </Card>
        ))}</section>}
      </main>

      <Modal open={Boolean(editor)} title={editor?.id ? "Edit hypothesis" : "Add hypothesis"} onCancel={() => setEditor(null)} onOk={() => void saveRule()} okText="Save hypothesis" confirmLoading={saving} width={700}>
        {editor && <div className="rule-editor">
          <label>Title<Input value={editor.title} maxLength={200} onChange={(event) => setEditor({ ...editor, title: event.target.value })} /></label>
          <label>Trader-provided hypothesis<TextArea rows={5} maxLength={5000} value={editor.text} onChange={(event) => setEditor({ ...editor, text: event.target.value })} /></label>
          <div className="rule-edit-row"><label>Research status<Select value={editor.status} onChange={(status) => setEditor({ ...editor, status })} options={STATUSES.map((status) => ({ value: status, label: statusLabel(status) }))} /></label><label>Source record (optional)<Select allowClear value={editor.sourceId ?? undefined} placeholder="No source linked" onChange={(value) => setEditor({ ...editor, sourceId: value ?? null })} options={[{ value: 1, label: "User-provided trader calendar examples" }]} /></label></div>
          <div className="rule-editor-heading"><span>Planetary combinations</span><Button size="small" onClick={() => setEditor({ ...editor, aspects: [...editor.aspects, { planet_1: "Moon", planet_2: "Venus", aspect_angle_degrees: 90 }] })}>Add combination</Button></div>
          {editor.aspects.map((aspect, index) => <div className="rule-aspect-edit" key={index}><Select value={aspect.planet_1} options={PLANETS.map((planet) => ({ value: planet, label: planet }))} onChange={(value) => changeAspect(index, "planet_1", value)} /><span>×</span><Select value={aspect.planet_2} options={PLANETS.map((planet) => ({ value: planet, label: planet }))} onChange={(value) => changeAspect(index, "planet_2", value)} /><Select value={aspect.aspect_angle_degrees} options={ASPECTS.map((item) => ({ value: item.angle, label: `${item.name} · ${item.angle}°` }))} onChange={(value) => changeAspect(index, "aspect_angle_degrees", value)} /><Button danger type="text" disabled={editor.aspects.length === 1} onClick={() => setEditor({ ...editor, aspects: editor.aspects.filter((_, current) => current !== index) })}>Remove</Button></div>)}
          <p className="palette-hint">Keep the trader’s original wording in the hypothesis text. A standard aspect label is used for the combination association.</p>
        </div>}
      </Modal>
    </div>
  );
}

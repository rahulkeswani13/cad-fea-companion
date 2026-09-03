import type { ToolResult } from "./types";

export function fmtNum(v: unknown, digits = 2): string | null {
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return n.toFixed(digits);
}

export function fmtK(n: unknown): string | null {
  const s = fmtNum(n, 0);
  return s == null ? null : Number(s).toLocaleString("en-US");
}

const STAMP_KEYS = ["max_von_mises_mpa", "expected_vs_actual", "safety_factor_vs_yield", "divergence_flag"];

/** Semantic stamp for a tool result: solver states own the colors. */
export function deriveStamp(r: Record<string, unknown>): "pass" | "caution" | "fail" | null {
  if (r.ok === false) return "fail";
  const isSolveLike = STAMP_KEYS.some((k) => k in r);
  if (!isSolveLike) return null;
  const eva = (r.expected_vs_actual ?? null) as Record<string, unknown> | null;
  const sf = Number(r.safety_factor_vs_yield ?? (eva?.safety_factor_vs_yield ?? NaN));
  const diverged = Boolean(r.divergence_flag ?? eva?.divergence_flag);
  if (Number.isFinite(sf) && sf < 1) return "fail";
  if (diverged) return "caution";
  if (Number.isFinite(sf) && sf < 1.5) return "caution";
  return "pass";
}

export interface KpiRow {
  key: string;
  label: string;
  value: string;
}

function addRow(rows: KpiRow[], key: string, label: string, value: string | null) {
  if (value != null && value !== "") rows.push({ key, label, value });
}

/** Compact KPI rows for a tool result (mirrors the legacy console's
 *  summarizeTool extraction, rendered as report-card rows). */
export function kpiRows(r: Record<string, unknown>): KpiRow[] {
  const rows: KpiRow[] = [];
  const abs = (v: unknown) => (v == null ? null : Math.abs(Number(v)));

  if (r.web_type != null) addRow(rows, "web_type", "variant", String(r.web_type));
  if (r.mass_kg != null) addRow(rows, "mass", "mass", `${fmtNum(abs(r.mass_kg), 3)} kg`);
  if (r.relative_density != null) addRow(rows, "rho", "ρ*", fmtNum(r.relative_density, 3));
  if (r.max_von_mises_mpa != null)
    addRow(rows, "sigma", "σ max", `${fmtNum(abs(r.max_von_mises_mpa), 2)} MPa`);
  if (r.max_vm_location_mm != null) {
    const loc = JSON.stringify(r.max_vm_location_mm);
    if (loc && loc !== "null" && loc.length < 40) addRow(rows, "loc", "σ @", loc);
  }
  if (r.safety_factor_vs_yield != null)
    addRow(rows, "sf", "SF yield", fmtNum(abs(r.safety_factor_vs_yield), 2));
  if (r.pad_deflection_mm != null)
    addRow(rows, "defl", "δ pad", `${fmtNum(abs(r.pad_deflection_mm), 3)} mm`);
  if (r.deflection_mm != null)
    addRow(rows, "defl", "δ tip", `${fmtNum(abs(r.deflection_mm), 3)} mm`);
  if (r.mesh_max_size_mm != null) addRow(rows, "mesh", "mesh max", `${fmtNum(r.mesh_max_size_mm, 1)} mm`);
  if (r.method != null) addRow(rows, "method", "method", String(r.method));

  const eva = r.expected_vs_actual as Record<string, unknown> | null | undefined;
  if (eva && typeof eva === "object") {
    addRow(rows, "eva_expected", "expected", fmtNum(eva.expected_stress_mpa ?? eva.expected, 2) ?? "—");
    addRow(rows, "eva_actual", "actual", fmtNum(eva.actual_stress_mpa ?? eva.actual, 2) ?? "—");
    addRow(rows, "eva_ratio", "ratio", fmtNum(eva.ratio, 2) ?? "—");
  }
  if (r.divergence_flag != null)
    addRow(rows, "divergence", "divergence", r.divergence_flag ? "FLAGGED" : "false");
  if (r.converged != null) addRow(rows, "converged", "converged", String(r.converged));

  const receipt = r.receipt as Record<string, unknown> | null | undefined;
  if (receipt && typeof receipt === "object" && receipt.elapsed_s != null)
    addRow(rows, "elapsed", "elapsed", `${fmtNum(receipt.elapsed_s, 2)} s`);

  return rows;
}

/** Honest caveats surfaced on the report card (solver-honesty pattern). */
export function caveatLines(r: Record<string, unknown>): string[] {
  const out: string[] = [];
  const push = (v: unknown) => {
    if (typeof v === "string" && v.trim()) out.push(v.trim());
  };
  if (Array.isArray(r.caveats)) r.caveats.forEach(push);
  if (Array.isArray(r.disclaimers)) r.disclaimers.forEach(push);
  if (typeof r.warning === "string") push(r.warning);
  const eva = r.expected_vs_actual as Record<string, unknown> | null | undefined;
  if (eva && typeof eva === "object") {
    if (Array.isArray(eva.caveats)) eva.caveats.forEach(push);
    if (Array.isArray(eva.assumptions)) eva.assumptions.forEach(push);
  }
  return [...new Set(out)];
}

/** One-line summary for compact contexts (palette footer, run log). */
export function toolSummary(t: ToolResult): string {
  const r = t.result ?? {};
  if (r.ok === false) {
    const err = String(r.error ?? r.warning ?? "failed").replace(/\s+/g, " ");
    return `${t.name}: failed — ${err.slice(0, 120)}`;
  }
  const rows = kpiRows(r);
  const bits = rows
    .filter((row) => ["sigma", "sf", "mass", "defl", "rho", "web_type", "method"].includes(row.key))
    .map((row) => `${row.label} ${row.value}`);
  return `${t.name}: ok — ${bits.length ? bits.join(", ") : "ok"}`;
}

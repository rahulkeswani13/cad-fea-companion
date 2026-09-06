import type { ToolResult } from "./types";

export function fmtNum(v: unknown, digits = 2): string | null {
  // null/"" must not coerce to 0 (Number(null) === 0): a missing value is
  // unavailable, never zero. Legitimate zeros pass through.
  if (v == null || v === "") return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return n.toFixed(digits);
}

export function fmtK(n: unknown): string | null {
  const s = fmtNum(n, 0);
  return s == null ? null : Number(s).toLocaleString("en-US");
}

export type Tone = "pass" | "caution" | "fail";

/** SF threshold tone shared by report cards and history rows. */
export function sfTone(sf: unknown): Tone | null {
  const v = Number(sf);
  if (!Number.isFinite(v)) return null;
  if (v < 1) return "fail";
  if (v < 1.5) return "caution";
  return "pass";
}

/** Curated plain-language names for the exposed tool registry
 *  (companion/tools/tool_schemas.py). Unmapped tools fall back to a
 *  prettified raw name; raw names stay inspectable in Technical details. */
const TOOL_NAMES: Record<string, string> = {
  create_brake_pedal: "Create brake pedal",
  create_uav_arm: "Create UAV arm",
  create_cantilever: "Create cantilever benchmark",
  apply_load_and_solve: "FEA solve",
  get_max_von_mises: "Peak stress lookup",
  run_convergence_study: "Mesh convergence study",
  compare_brake_pedal_variants: "Compare pedal variants",
  compare_materials: "Compare materials",
  get_design_program: "Read design program",
  update_design_program: "Update design program",
  get_lattice_metrics: "Lattice metrics",
  query_results: "Run history query",
  open_in_freecad: "Open in FreeCAD",
};

export function friendlyToolName(name: string): string {
  const curated = TOOL_NAMES[name];
  if (curated) return curated;
  return name.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());
}

export type MethodStamp = "estimate" | "reference" | "fallback";

export interface MethodDescriptor {
  /** Plain-language origin label; null when the wire carries no confident
   *  evidence (the raw method string is shown as-is instead). */
  label: string | null;
  stamp: MethodStamp | null;
}

/**
 * Origin of a result, read only from fields the wire already carries
 * (method / fallback — never invented). Precedence:
 *   explicit analytical → Analytical estimate
 *   explicit saved/precomputed source → Saved reference result
 *   fallback with unclear origin → Fallback result
 *   CalculiX without fallback → Live simulation
 * A fallback flag always overrides a live-sounding label (the fallback
 * branch is checked before the CalculiX branch), and fallback is never
 * equated with analytical.
 */
export function describeMethod(r: Record<string, unknown>): MethodDescriptor {
  const method = String(r.method ?? "").toLowerCase();
  const fallback = r.fallback === true;
  if (method.includes("analytical")) return { label: "Analytical estimate", stamp: "estimate" };
  if (method.includes("precomputed") || method.includes("saved"))
    return { label: "Saved reference result", stamp: "reference" };
  if (fallback) return { label: "Fallback result", stamp: "fallback" };
  if (method.includes("calculix")) return { label: "Live simulation", stamp: null };
  return { label: null, stamp: null };
}

export interface KpiRow {
  key: string;
  label: string;
  value: string;
  /** Colored value (SF thresholds); unset renders neutral. */
  tone?: Tone;
  /** Origin stamp rendered beside the value (ESTIMATE/REFERENCE/FALLBACK). */
  stamp?: MethodStamp;
}

function addRow(rows: KpiRow[], key: string, label: string, value: string | null) {
  if (value != null && value !== "") rows.push({ key, label, value });
}

/** "12.0 MPa", or an explicit "—" when the field is present but
 *  unavailable. Absent keys are omitted by the caller. */
function withUnit(v: unknown, digits: number, unit: string): string {
  const s = fmtNum(v, digits);
  return s == null ? "—" : `${s} ${unit}`;
}

/** Compact KPI rows for a tool result (mirrors the legacy console's
 *  summarizeTool extraction, rendered as report-card rows). */
export function kpiRows(r: Record<string, unknown>): KpiRow[] {
  const rows: KpiRow[] = [];
  const abs = (v: unknown) => (v == null ? null : Math.abs(Number(v)));

  if (r.web_type != null) addRow(rows, "web_type", "variant", String(r.web_type));
  if ("mass_kg" in r) addRow(rows, "mass", "mass", withUnit(abs(r.mass_kg), 3, "kg"));
  if ("relative_density" in r) addRow(rows, "rho", "ρ*", withUnit(r.relative_density, 3, ""));
  if ("max_von_mises_mpa" in r)
    addRow(rows, "sigma", "σ max", withUnit(abs(r.max_von_mises_mpa), 2, "MPa"));
  if (r.max_vm_location_mm != null) {
    const loc = JSON.stringify(r.max_vm_location_mm);
    if (loc && loc !== "null" && loc.length < 40) addRow(rows, "loc", "σ @", loc);
  }
  if ("safety_factor_vs_yield" in r) {
    const raw = r.safety_factor_vs_yield ?? (r.expected_vs_actual as any)?.safety_factor_vs_yield;
    rows.push({
      key: "sf",
      label: "SF yield",
      value: fmtNum(raw == null ? null : Math.abs(Number(raw)), 2) ?? "—",
      tone: sfTone(raw) ?? undefined,
    });
  }
  if ("pad_deflection_mm" in r)
    addRow(rows, "defl-pad", "δ pad", withUnit(abs(r.pad_deflection_mm), 3, "mm"));
  if ("tip_deflection_mm" in r)
    addRow(rows, "defl-tip", "δ tip", withUnit(abs(r.tip_deflection_mm), 3, "mm"));
  if ("deflection_mm" in r)
    addRow(rows, "defl", "δ", withUnit(abs(r.deflection_mm), 3, "mm"));
  if ("mesh_max_size_mm" in r)
    addRow(rows, "mesh", "mesh max", withUnit(r.mesh_max_size_mm, 1, "mm"));

  // Origin row: rendered whenever the wire carries method/fallback evidence,
  // even when the raw method string itself is absent (fallback flag alone).
  const md = describeMethod(r);
  if ("method" in r || r.fallback === true || md.stamp) {
    const raw = r.method != null ? String(r.method) : null;
    rows.push({
      key: "method",
      label: "source",
      value: md.label ?? raw ?? "—",
      stamp: md.stamp ?? undefined,
    });
  }

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

/** Honest caveats surfaced on the report card (solver-honesty pattern).
 *  `note` is included: fallback results carry their honesty caveat there
 *  (e.g. "Coarse tets under-predict peak strut stress"). */
export function caveatLines(r: Record<string, unknown>): string[] {
  const out: string[] = [];
  const push = (v: unknown) => {
    if (typeof v === "string" && v.trim()) out.push(v.trim());
  };
  if (Array.isArray(r.caveats)) r.caveats.forEach(push);
  if (Array.isArray(r.disclaimers)) r.disclaimers.forEach(push);
  if (typeof r.warning === "string") push(r.warning);
  if (typeof r.note === "string") push(r.note);
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
    return `${friendlyToolName(t.name)}: failed — ${err.slice(0, 120)}`;
  }
  const rows = kpiRows(r);
  const bits = rows
    .filter((row) =>
      ["sigma", "sf", "mass", "defl", "defl-pad", "defl-tip", "rho", "web_type", "method"].includes(
        row.key,
      ),
    )
    .map((row) => `${row.label} ${row.value}`);
  return `${friendlyToolName(t.name)}: ok — ${bits.length ? bits.join(", ") : "ok"}`;
}

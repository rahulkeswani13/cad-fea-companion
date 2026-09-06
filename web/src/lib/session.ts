import type { RunRow, ToolResult } from "./types";

/**
 * Runs observed in this frontend session (ADR-017 PR 3). Built only from
 * solve operations actually observed in tool results — historical query
 * results are excluded, run ids are deduplicated (convergence replays the
 * base run), sub-runs are included, and a solve without a run id displays
 * with an `unrecorded` marker instead of an invented identity.
 */

const SOLVE_KPI_KEYS = ["max_von_mises_mpa", "safety_factor_vs_yield", "mesh_max_size_mm"];

export interface SessionRun extends RunRow {
  /** Solve recorded no run id (e.g. history_write_error) — shown, not invented. */
  unrecorded?: boolean;
  /** Failed mesh attempt (convergence sub-step) — shown as failed. */
  failed?: boolean;
}

function solveLike(r: Record<string, unknown>): boolean {
  return r.run_id != null || SOLVE_KPI_KEYS.some((k) => k in r);
}

function rowFrom(r: Record<string, unknown>, observedAt: string): SessionRun {
  const runId = typeof r.run_id === "string" ? r.run_id : null;
  return {
    run_id: runId ?? undefined,
    part: typeof r.part === "string" ? r.part : undefined,
    web_type: typeof r.web_type === "string" ? r.web_type : undefined,
    force_n: typeof r.force_n === "number" ? r.force_n : undefined,
    method: typeof r.method === "string" ? r.method : undefined,
    max_von_mises_mpa:
      typeof r.max_von_mises_mpa === "number" ? r.max_von_mises_mpa : undefined,
    safety_factor_vs_yield:
      typeof r.safety_factor_vs_yield === "number" ? r.safety_factor_vs_yield : undefined,
    mesh_max_size_mm: typeof r.mesh_max_size_mm === "number" ? r.mesh_max_size_mm : undefined,
    divergence_flag: r.divergence_flag === true,
    ts: observedAt,
    unrecorded: !runId,
    failed: r.ok === false,
  };
}

/** Extract new session runs from one final payload's tool results. Mutates
 *  `seen` with any newly observed run ids. */
export function extractSessionRuns(
  toolResults: ToolResult[] | undefined,
  seen: Set<string>,
  observedAt: string,
): SessionRun[] {
  const out: SessionRun[] = [];
  for (const tr of toolResults ?? []) {
    if (tr.name === "query_results") continue; // historical query, not a session solve
    const r = (tr.result ?? {}) as Record<string, unknown>;
    if (typeof r !== "object" || r === null) continue;
    const candidates: Record<string, unknown>[] = [];
    if (solveLike(r)) candidates.push(r);
    if (Array.isArray(r.runs)) {
      for (const sub of r.runs) {
        if (sub && typeof sub === "object" && (solveLike(sub) || (sub as Record<string, unknown>).ok === false)) {
          candidates.push(sub as Record<string, unknown>);
        }
      }
    }
    for (const c of candidates) {
      const runId = typeof c.run_id === "string" ? c.run_id : null;
      if (runId) {
        if (seen.has(runId)) continue;
        seen.add(runId);
      }
      out.push(rowFrom(c, observedAt));
    }
  }
  return out;
}

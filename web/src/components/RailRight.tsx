import type { DesignProgram, RunRow, RunsPayload, SolverStatus } from "../lib/types";
import { fmtNum, sfTone, type Tone } from "../lib/format";
import type { SessionRun } from "../lib/session";
import { SectionLabel, Stamp, Switch } from "./primitives";

const TONE_CLASS: Record<Tone, string> = {
  pass: "text-pass",
  caution: "text-caution",
  fail: "text-fail",
};

/** 03 saved workspace design — the persisted parametric source of truth
 *  (F04). Global by design: the design program on disk is the accepted
 *  revision, which may belong to another session (ADR-017 PR 3). */
export function DesignProgramCard({ program }: { program: DesignProgram | null }) {
  const active = program?.part ?? program?.active_part ?? null;
  return (
    <section className="px-3 py-3" data-testid="design-program">
      <SectionLabel index="03" title="Saved workspace design" />
      <p className="pb-1 font-mono text-[9.5px] leading-relaxed text-ink-faint">
        Saved workspace state — may belong to another session.
      </p>
      {active && program?.rev != null ? (
        <>
          <div className="flex items-baseline justify-between py-2">
            <span className="font-display text-[15px] font-semibold tracking-[0.02em] text-ink">
              {active}
            </span>
            <span className="font-mono text-[11px] text-ink-dim">rev {program.rev}</span>
          </div>
          <dl>
            {program.params.map((p) => (
              <div key={p.key} className="data-row border-b border-line/60 last:border-b-0">
                <dt className="data-key">{p.key}</dt>
                <dd className="data-val">{String(p.value)}</dd>
              </div>
            ))}
          </dl>
          {program.params_hash && (
            <div className="pt-2 font-mono text-[10px] text-ink-faint">
              sha256 {program.params_hash.slice(0, 12)}…
            </div>
          )}
        </>
      ) : (
        <p className="pt-2 font-mono text-[11px] leading-relaxed text-ink-faint">
          {program?.error ?? program?.note ?? "No design program on disk yet — create a part."}
        </p>
      )}
    </section>
  );
}

function RunGrid({ rows }: { rows: (RunRow | SessionRun)[] }) {
  return (
    <div className="pt-1">
      <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-3 border-b border-line pb-1 font-mono text-[9.5px] tracking-[0.1em] text-ink-faint uppercase">
        <span>run</span>
        <span className="text-right">σ MPa</span>
        <span className="text-right">SF</span>
        <span className="text-right">flag</span>
      </div>
      {rows.map((run, idx) => {
        const tone = sfTone(run.safety_factor_vs_yield);
        const failed = (run as SessionRun).failed === true;
        const unrecorded = (run as SessionRun).unrecorded === true;
        return (
          <div
            key={run.run_id ?? `${run.ts ?? "run"}-${idx}`}
            className="grid grid-cols-[1fr_auto_auto_auto] items-baseline gap-x-3 border-b border-line/60 py-1.5 last:border-b-0"
          >
            <span className="min-w-0">
              <span className="block truncate font-mono text-[11px] text-ink">
                {run.web_type ?? run.part ?? "run"}
              </span>
              <span className="block truncate font-mono text-[9.5px] text-ink-faint">
                {run.ts ?? run.run_id ?? ""}
                {run.method ? ` · ${run.method}` : ""}
                {run.run_id && run.ts ? ` · id ${run.run_id}` : ""}
              </span>
            </span>
            <span className="text-right font-mono text-[11px] text-ink">
              {fmtNum(run.max_von_mises_mpa, 1) ?? "—"}
            </span>
            <span
              className={`text-right font-mono text-[11px] ${tone ? TONE_CLASS[tone] : "text-ink"}`}
            >
              {fmtNum(run.safety_factor_vs_yield, 2) ?? "—"}
            </span>
            <span className="text-right">
              {failed ? (
                <Stamp kind="fail" label="failed" />
              ) : run.divergence_flag ? (
                <Stamp kind="caution" label="diverged" />
              ) : unrecorded ? (
                <Stamp kind="neutral" label="unrecorded" />
              ) : null}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** 04 runs in this session — solve operations observed during this
 *  frontend session only (ADR-017 PR 3): arrival order, run_id dedup,
 *  convergence sub-runs included, failed mesh attempts visible. Historical
 *  query results never become session runs. */
export function SessionRunsCard({ sessionRuns }: { sessionRuns: SessionRun[] }) {
  return (
    <section className="px-3 py-3" data-testid="session-runs">
      <SectionLabel index="04" title="Runs in this session" />
      {sessionRuns.length === 0 ? (
        <p className="pt-2 font-mono text-[11px] text-ink-faint">
          No solves yet in this session.
        </p>
      ) : (
        <RunGrid rows={sessionRuns} />
      )}
    </section>
  );
}

/** 05 solver status — what the machine can actually reach right now. */
export function SolverStatusCard({
  solver,
  onToggleConfirm,
}: {
  solver: SolverStatus | null;
  onToggleConfirm?: (next: boolean) => void;
}) {
  const confirmOn = solver?.require_tool_confirm === true;
  return (
    <section className="px-3 py-3" data-testid="solver-status">
      <SectionLabel index="05" title="Solver status" />
      <div className="pt-1">
        <StatusRow
          label="FreeCAD"
          ok={solver ? solver.freecad : null}
          value={solver?.freecad_cmd ? "cmd found" : "missing"}
        />
        <StatusRow
          label="LLM"
          ok={solver ? solver.llm.configured === true : null}
          value={solver?.llm.provider ?? "…"}
        />
        <div className="flex items-center justify-between py-1.5" data-testid="hitl-row">
          <span className="font-mono text-[10.5px] tracking-[0.1em] text-ink-faint uppercase">
            HITL gate
          </span>
          <span className="flex items-center gap-2 font-mono text-[11px] text-ink">
            {solver ? (confirmOn ? "confirm each tool" : "auto") : "…"}
            <Switch
              checked={confirmOn}
              onToggle={(next) => onToggleConfirm?.(next)}
              label="FreeCAD tool confirmation (HITL)"
              title="Require operator approval before FreeCAD tools run (ADR-016)"
              testid="hitl-toggle"
            />
          </span>
        </div>
      </div>
    </section>
  );
}

/** Right rail composite: saved workspace design · runs in this session (+ saved
 *  disclosure) · solver status. */
export function RailRight({
  program,
  runs,
  solver,
  sessionRuns,
  onToggleConfirm,
}: {
  program: DesignProgram | null;
  runs: RunsPayload | null;
  solver: SolverStatus | null;
  sessionRuns: SessionRun[];
  onToggleConfirm?: (next: boolean) => void;
}) {
  const savedRows = runs?.runs ?? [];
  return (
    <div className="flex min-h-full flex-col">
      <DesignProgramCard program={program} />
      <div className="hairline-t" />
      <SessionRunsCard sessionRuns={sessionRuns} />
      <div className="hairline-t" />
      <section className="px-3 py-3" data-testid="run-history">
        <details data-testid="saved-runs">
          <summary className="cursor-pointer select-none font-mono text-[10.5px] tracking-[0.1em] text-ink-dim uppercase transition-colors duration-150 hover:text-ink">
            Recent saved runs
          </summary>
          <div className="pt-2 font-mono text-[9.5px] text-ink-faint">
            {runs?.part ? `part: ${runs.part}` : "no part selected"} · latest {Math.min(savedRows.length, 8)} records
          </div>
          {savedRows.length === 0 ? (
            <p className="pt-2 font-mono text-[11px] text-ink-faint">
              {runs?.error ?? "No saved runs returned."}
            </p>
          ) : (
            <RunGrid rows={savedRows.slice(0, 8)} />
          )}
        </details>
      </section>
      <div className="hairline-t" />
      <SolverStatusCard solver={solver} onToggleConfirm={onToggleConfirm} />
    </div>
  );
}

function StatusRow({ label, ok, value }: { label: string; ok: boolean | null; value: string }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="font-mono text-[10.5px] tracking-[0.1em] text-ink-faint uppercase">{label}</span>
      <span className="flex items-center gap-1.5 font-mono text-[11px] text-ink">
        {value}
        <span
          className={`inline-block h-1.5 w-1.5 rounded-full ${
            ok == null ? "bg-ink-faint" : ok ? "bg-pass" : "bg-caution"
          }`}
        />
      </span>
    </div>
  );
}

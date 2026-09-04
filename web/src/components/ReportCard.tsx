import { caveatLines, deriveStamp, kpiRows } from "../lib/format";
import type { ToolResult } from "../lib/types";
import { Stamp } from "./primitives";

/**
 * The signature detail (ADR-015): every tool result renders as a test-report
 * card — tool name, semantic stamp, KPI rows, honest caveats. FEA solves get
 * the solver-honesty treatment: method, mesh, divergence, NOT VERIFIED.
 */
export function ReportCard({ tr }: { tr: ToolResult }) {
  const r = tr.result ?? {};
  const stamp = deriveStamp(r);
  const failed = r.ok === false;
  const rows = kpiRows(r);
  const caveats = caveatLines(r);
  const correction = typeof r.correction === "string" ? r.correction : null;
  const error = typeof r.error === "string" ? r.error : null;

  return (
    <div className="stamp-in overflow-hidden rounded-[4px] border border-line bg-panel" data-testid="report-card">
      <div className="flex items-center gap-2 border-b border-line bg-raised/60 px-3 py-1.5">
        <span className="font-mono text-[11px] font-semibold tracking-[0.06em] text-ink">
          {tr.name}
        </span>
        <span className="ml-auto">
          {stamp && (
            <Stamp
              kind={stamp}
              label={stamp === "pass" ? "PASS" : stamp === "caution" ? "CAUTION" : "FAIL"}
            />
          )}
          {!stamp && !failed && <Stamp kind="neutral" label="OK" />}
        </span>
      </div>

      {failed && (
        <div className="border-b border-line px-3 py-2">
          <div className="font-mono text-[11.5px] leading-relaxed text-fail">{error}</div>
          {correction && (
            <div className="mt-1 text-[12px] leading-relaxed text-ink-dim">
              <span className="font-mono text-[10px] tracking-[0.1em] text-caution uppercase">
                correction
              </span>{" "}
              {correction}
            </div>
          )}
        </div>
      )}

      {rows.length > 0 && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 px-3 py-2">
          {rows.map((row) => (
            <div key={row.key} className="col-span-2 grid grid-cols-subgrid items-baseline py-px">
              <dt className="font-mono text-[10.5px] tracking-[0.08em] text-ink-faint uppercase">
                {row.label}
              </dt>
              <dd className="text-right font-mono text-[12px] text-ink">{row.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {caveats.length > 0 && (
        <div className="border-t border-line px-3 py-2">
          {caveats.map((c, i) => (
            <div key={i} className="flex items-start gap-2 py-px text-[12px] leading-relaxed text-caution">
              <Stamp kind="caution" label="NOT VERIFIED" />
              <span className="text-ink-dim">{c}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

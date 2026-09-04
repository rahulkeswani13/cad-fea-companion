import type { HealthPayload } from "../lib/types";
import { Dot, Moon, PanelsLeft, PanelsRight, Plus, Sun } from "../lib/icons";
import { Btn, IconBtn } from "./primitives";

function Cell({
  label,
  value,
  tone = "ink",
  title,
}: {
  label: string;
  value: string;
  tone?: "ink" | "pass" | "caution";
  title?: string;
}) {
  const toneCls =
    tone === "pass" ? "text-pass" : tone === "caution" ? "text-caution" : "text-ink";
  return (
    <div
      className="flex items-baseline gap-2 border-l border-line px-3 py-2 first:border-l-0"
      title={title}
    >
      <span className="font-mono text-[10px] tracking-[0.12em] text-ink-faint uppercase">{label}</span>
      <span className={`truncate font-mono text-[11px] ${toneCls}`}>{value}</span>
    </div>
  );
}

export function TopBar({
  health,
  threadId,
  tokens,
  leftOpen,
  rightOpen,
  theme,
  onToggleLeft,
  onToggleRight,
  onToggleTheme,
  onNewSession,
}: {
  health: HealthPayload | null;
  threadId: string;
  tokens: number;
  turns?: number;
  leftOpen: boolean;
  rightOpen: boolean;
  theme: "dark" | "light";
  onToggleLeft: () => void;
  onToggleRight: () => void;
  onToggleTheme: () => void;
  onNewSession: () => void;
}) {
  const llm = health?.llm;
  const llmReady = llm?.configured === true;
  const freecadOk = Boolean(health?.freecad_cmd);
  const hitl = health?.agent?.require_tool_confirm === true;
  return (
    <header className="hairline-b flex items-stretch bg-panel">
      <div className="flex items-center gap-2 px-3">
        <IconBtn title="Toggle prompt rail" onClick={onToggleLeft} active={leftOpen}>
          <PanelsLeft />
        </IconBtn>
        <IconBtn title="Toggle state rail" onClick={onToggleRight} active={rightOpen}>
          <PanelsRight />
        </IconBtn>
      </div>

      <div className="flex min-w-0 items-baseline gap-3 px-3 py-2">
        <h1 className="font-display text-[15px] font-semibold tracking-[0.04em] whitespace-nowrap uppercase">
          CAD/FEA Companion
        </h1>
        <span className="hidden font-mono text-[10px] tracking-[0.14em] text-ink-faint uppercase lg:inline">
          operator console
        </span>
      </div>

      <div className="ml-auto hidden items-stretch md:flex" data-testid="status-readout">
        <Cell
          label="LLM"
          value={llm ? `${llm.provider ?? "?"} ${llmReady ? "ready" : "needs key"}` : "…"}
          tone={llmReady ? "pass" : "caution"}
        />
        <Cell
          label="FreeCAD"
          value={freecadOk ? "found" : "missing"}
          tone={freecadOk ? "pass" : "caution"}
        />
        <Cell label="Model" value={llm?.model || "-"} title={llm?.model || undefined} />
        <Cell label="HITL" value={hitl ? "on" : "off"} tone={hitl ? "pass" : "ink"} />
        <Cell label="Thread" value={threadId.slice(0, 8)} title={threadId} />
        <Cell label="Tokens" value={tokens.toLocaleString("en-US")} />
      </div>

      <div className="flex items-center gap-2 px-3">
        <IconBtn
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          onClick={onToggleTheme}
          testid="theme-toggle"
        >
          {theme === "dark" ? <Sun /> : <Moon />}
        </IconBtn>
        <Btn variant="outline" onClick={onNewSession} title="Reset thread and clear the log">
          <Plus size={12} /> Session
        </Btn>
      </div>
    </header>
  );
}

export function StatusDot({ ok }: { ok: boolean }) {
  return <Dot className={ok ? "text-pass" : "text-caution"} />;
}

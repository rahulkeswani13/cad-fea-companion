import { useCallback, useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import {
  fetchDesignProgram,
  fetchHealth,
  fetchPrompts,
  fetchRuns,
  fetchSolverStatus,
  resumeChat,
  streamChat,
} from "./lib/api";
import { renderMarkdown } from "./lib/markdown";
import type {
  ChatMessage,
  DesignProgram,
  FinalPayload,
  HealthPayload,
  InterruptState,
  PromptItem,
  PromptLibrary,
  RunsPayload,
  SolverStatus,
  ToolResult,
} from "./lib/types";
import { TopBar } from "./components/TopBar";
import { RailLeft } from "./components/RailLeft";
import { RailRight } from "./components/RailRight";
import { Message } from "./components/Message";
import { Composer } from "./components/Composer";
import { CommandPalette } from "./components/CommandPalette";
import { Btn, RailHandle, Stamp } from "./components/primitives";
import type { PickOptions } from "./components/PromptMenu";

const THREAD_KEY = "cad_fea_thread_id";

/** Rail width with localStorage persistence, drag resize. Max is a live
 *  share of the viewport, capped so the chat column stays usable (the
 *  caller supplies the other rail's width via getExtraMax). */
function useRailWidth(
  key: string,
  def: number,
  min: number,
  maxShare: number,
  dir: 1 | -1,
  getExtraMax?: () => number,
) {
  const clamp = useCallback(
    (v: number) => {
      const shareMax = Math.round(window.innerWidth * maxShare);
      const max = Math.min(shareMax, getExtraMax?.() ?? shareMax);
      return Math.min(max, Math.max(min, v));
    },
    [min, maxShare, getExtraMax],
  );
  const [w, setW] = useState(() => {
    // Init only applies the viewport share — the cross-rail guard reads the
    // other rail's state, which isn't up yet during mount.
    const max = Math.round(window.innerWidth * maxShare);
    return Math.min(max, Math.max(min, Number(localStorage.getItem(key)) || def));
  });
  useEffect(() => {
    localStorage.setItem(key, String(w));
  }, [key, w]);
  const startDrag = useCallback(
    (e: ReactPointerEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startW = w;
      const onMove = (ev: PointerEvent) =>
        setW(clamp(startW + dir * (ev.clientX - startX)));
      const onUp = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        document.body.style.userSelect = "";
        document.body.style.cursor = "";
      };
      document.body.style.userSelect = "none";
      document.body.style.cursor = "col-resize";
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    },
    [clamp, dir, w],
  );
  return { w, startDrag, reset: () => setW(def) };
}

function getThreadId(): string {
  let id = localStorage.getItem(THREAD_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(THREAD_KEY, id);
  }
  return id;
}

let nextMsgId = 1;

function finalToMessage(data: FinalPayload, failed: boolean): ChatMessage {
  const toolResults = (data.tool_results ?? []) as ToolResult[];
  return {
    id: nextMsgId++,
    role: "assistant",
    html: data.answer ? renderMarkdown(data.answer) : undefined,
    text: !data.answer ? (data.error || "No answer") : undefined,
    toolResults,
    citations: data.citations ?? [],
    grounding: data.grounding,
    stamp: failed ? "fail" : undefined,
  };
}

export default function App() {
  const [threadId, setThreadId] = useState(getThreadId);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [library, setLibrary] = useState<PromptLibrary | null>(null);
  const [program, setProgram] = useState<DesignProgram | null>(null);
  const [runs, setRuns] = useState<RunsPayload | null>(null);
  const [solver, setSolver] = useState<SolverStatus | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [composer, setComposer] = useState("");
  const [busy, setBusy] = useState(false);
  const [interrupt, setInterrupt] = useState<InterruptState | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [activeFeature, setActiveFeature] = useState<string | null>(null);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [theme, setTheme] = useState<"dark" | "light">(() =>
    localStorage.getItem("cad_fea_theme") === "light" ? "light" : "dark",
  );
  // Chat column keeps >= 380px; rails may still cover well over half the screen.
  const centerMin = 380;
  const leftRail = useRailWidth("cad_fea_left_w", 280, 220, 0.7, 1, () =>
    window.innerWidth - centerMin - (rightOpen ? rightRail.w : 0),
  );
  const rightRail = useRailWidth("cad_fea_right_w", 320, 260, 0.7, -1, () =>
    window.innerWidth - centerMin - (leftOpen ? leftRail.w : 0),
  );
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "light") root.setAttribute("data-theme", "light");
    else root.removeAttribute("data-theme");
    localStorage.setItem("cad_fea_theme", theme);
  }, [theme]);

  const refreshStatus = useCallback(async () => {
    try {
      setHealth(await fetchHealth());
    } catch {
      setHealth(null);
    }
  }, []);

  const refreshRails = useCallback(async () => {
    try {
      setProgram(await fetchDesignProgram());
    } catch {
      setProgram(null);
    }
    try {
      setRuns(await fetchRuns());
    } catch {
      setRuns(null);
    }
    try {
      setSolver(await fetchSolverStatus());
    } catch {
      setSolver(null);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    refreshRails();
    fetchPrompts()
      .then(setLibrary)
      .catch(() => setLibrary(null));
  }, [refreshStatus, refreshRails]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [messages, interrupt]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const typing =
        target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT");
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      } else if (e.key === "/" && !typing && !paletteOpen) {
        e.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen]);

  const applyFinal = useCallback(
    (data: FinalPayload) => {
      if (data.thread_id) {
        localStorage.setItem(THREAD_KEY, data.thread_id);
        setThreadId(data.thread_id);
      }
      if (data.interrupted) {
        const raw = data.interrupt as { tool_calls?: { name?: string }[] } | null;
        const calls = raw?.tool_calls ?? (Array.isArray(raw) ? raw : []) ?? [];
        const names = calls.map((c) => c?.name ?? "").filter(Boolean);
        setInterrupt({ toolNames: names });
        setMessages((m) => [
          ...m,
          {
            id: nextMsgId++,
            role: "assistant",
            text: "Paused for FreeCAD tool confirmation (HITL).",
          },
        ]);
      } else {
        setMessages((m) => [...m, finalToMessage(data, Boolean(data.error))]);
      }
      refreshStatus();
      refreshRails();
    },
    [refreshRails, refreshStatus],
  );

  const send = useCallback(
    async (raw: string) => {
      const message = raw.trim();
      if (!message || busy) return;
      setBusy(true);
      setPaletteOpen(false);
      setComposer("");
      const statusId = nextMsgId++;
      setMessages((m) => [
        ...m,
        { id: nextMsgId++, role: "user", text: message },
        { id: statusId, role: "status", text: "Starting…" },
      ]);
      const setStatus = (t: string) =>
        setMessages((m) => m.map((msg) => (msg.id === statusId ? { ...msg, text: t } : msg)));
      try {
        const data = await streamChat(message, threadId, setStatus);
        setMessages((m) => m.filter((msg) => msg.id !== statusId));
        applyFinal(data);
      } catch (err) {
        setMessages((m) => [
          ...m.filter((msg) => msg.id !== statusId),
          { id: nextMsgId++, role: "assistant", text: `Request failed: ${err}` },
        ]);
      } finally {
        setBusy(false);
      }
    },
    [applyFinal, busy, threadId],
  );

  const resume = useCallback(
    async (approved: boolean) => {
      setBusy(true);
      setInterrupt(null);
      const statusId = nextMsgId++;
      setMessages((m) => [
        ...m,
        {
          id: statusId,
          role: "status",
          text: approved ? "Resuming after approve…" : "Resuming after reject…",
        },
      ]);
      try {
        const data = await resumeChat(threadId, approved);
        setMessages((m) => m.filter((msg) => msg.id !== statusId));
        applyFinal(data as FinalPayload);
      } catch (err) {
        setMessages((m) => [
          ...m.filter((msg) => msg.id !== statusId),
          { id: nextMsgId++, role: "assistant", text: `Resume failed: ${err}` },
        ]);
      } finally {
        setBusy(false);
      }
    },
    [applyFinal, threadId],
  );

  const onPick = useCallback(
    (item: PromptItem, opts: PickOptions) => {
      if (opts.send) {
        send(item.prompt);
      } else {
        setPaletteOpen(false);
        setComposer(item.prompt);
      }
    },
    [send],
  );

  function newSession() {
    const id = crypto.randomUUID();
    localStorage.setItem(THREAD_KEY, id);
    setThreadId(id);
    setMessages([]);
    setInterrupt(null);
    refreshStatus();
    refreshRails();
  }

  const usage = health?.session_usage?.threads?.[threadId];
  const tokens = usage?.total_tokens ?? 0;

  return (
    <div className="flex h-screen flex-col">
      <TopBar
        health={health}
        threadId={threadId}
        tokens={tokens}
        leftOpen={leftOpen}
        rightOpen={rightOpen}
        theme={theme}
        onToggleLeft={() => setLeftOpen((o) => !o)}
        onToggleRight={() => setRightOpen((o) => !o)}
        onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        onNewSession={newSession}
      />

      <div className="flex min-h-0 flex-1">
        {leftOpen && (
          <aside
            data-testid="rail-left"
            className="hairline-r relative shrink-0 bg-panel"
            style={{ width: leftRail.w }}
          >
            <div className="absolute inset-0 overflow-y-auto">
              <RailLeft
                library={library}
                onPick={(prompt) => send(prompt)}
                activeFeature={activeFeature}
                onSelectFeature={setActiveFeature}
              />
            </div>
            <RailHandle rail="left" edge="right" onDrag={leftRail.startDrag} onReset={leftRail.reset} />
          </aside>
        )}

        <main className="flex min-w-0 flex-1 flex-col">
          <div ref={logRef} className="min-h-0 flex-1 overflow-y-auto" data-testid="chat-log">
            {messages.length === 0 ? (
              <div className="mx-auto flex h-full max-w-[72ch] flex-col justify-center px-6">
                <p className="font-mono text-[10px] tracking-[0.16em] text-ink-faint uppercase">
                  agent loop · retrieve → agent ⇄ tools
                </p>
                <h2 className="mt-2 font-display text-[26px] leading-tight font-semibold text-ink">
                  Parametric CAD, meshing and FEA solves.
                </h2>
                <p className="mt-3 max-w-[58ch] text-[13px] leading-relaxed text-ink-dim">
                  Open the prompt palette{" "}
                  <span className="font-mono text-[11.5px] text-accent">⌘K</span> for the scripted
                  library, or pick a feature walkthrough in the left rail. FEA answers arrive as
                  report cards stating method, mesh and what was not verified.
                </p>
              </div>
            ) : (
              <div className="mx-auto max-w-[860px] space-y-5 px-6 py-6">
                {messages.map((msg) => (
                  <Message key={msg.id} msg={msg} />
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-line bg-bg px-4 py-3">
            <div className="mx-auto max-w-[860px]">
              {interrupt && (
                <div
                  data-testid="confirm-bar"
                  className="stamp-in mb-2 flex items-center gap-3 rounded-[4px] border border-caution/40 bg-panel px-3 py-2"
                >
                  <Stamp kind="caution" label="confirm" />
                  <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-ink-dim">
                    OK to run {interrupt.toolNames.join(", ") || "FreeCAD tool(s)"}?
                  </span>
                  <Btn variant="solid" onClick={() => resume(true)}>
                    Approve
                  </Btn>
                  <Btn variant="outline" onClick={() => resume(false)}>
                    Reject
                  </Btn>
                </div>
              )}
              <Composer
                value={composer}
                onChange={setComposer}
                onSend={() => send(composer)}
                busy={busy}
                library={library}
                onPick={onPick}
              />
              <div className="flex items-center justify-between px-1 pt-1.5 font-mono text-[10px] text-ink-faint">
                <span>enter sends · shift+enter newline</span>
                <span>
                  {library
                    ? `${library.categories.reduce((n, c) => n + c.items.length, 0)} library prompts · ${library.features.length} walkthroughs`
                    : "library offline"}
                </span>
              </div>
            </div>
          </div>
        </main>

        {rightOpen && (
          <aside
            data-testid="rail-right"
            className="hairline-l relative shrink-0 bg-panel"
            style={{ width: rightRail.w }}
          >
            <div className="absolute inset-0 overflow-y-auto">
              <RailRight program={program} runs={runs} solver={solver} />
            </div>
            <RailHandle rail="right" edge="left" onDrag={rightRail.startDrag} onReset={rightRail.reset} />
          </aside>
        )}
      </div>

      {paletteOpen && library && (
        <CommandPalette
          library={library}
          onPick={onPick}
          onClose={() => setPaletteOpen(false)}
        />
      )}
    </div>
  );
}

import { useRef, useState } from "react";
import type { PromptItem, PromptLibrary } from "../lib/types";
import { ChevronDown, SendMark } from "../lib/icons";
import { PromptMenu, type PickOptions } from "./PromptMenu";

export function Composer({
  value,
  onChange,
  onSend,
  busy,
  library,
  onPick,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  busy: boolean;
  library: PromptLibrary | null;
  onPick: (item: PromptItem, opts: PickOptions) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!busy && value.trim()) onSend();
    }
  }

  return (
    <form
      className="relative flex items-end gap-2 border border-line rounded-[4px] bg-panel p-2 transition-colors duration-150 focus-within:border-line-strong"
      onSubmit={(e) => {
        e.preventDefault();
        if (!busy && value.trim()) onSend();
      }}
    >
      {menuOpen && library && (
        <PromptMenu library={library} onPick={onPick} onClose={() => setMenuOpen(false)} />
      )}

      <button
        type="button"
        data-testid="prompts-button"
        onClick={() => setMenuOpen((o) => !o)}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-[2px] border border-line px-2.5 py-2 font-mono text-[11px] tracking-[0.08em] text-ink-dim uppercase transition-colors duration-150 hover:border-accent hover:text-accent"
      >
        Prompts
        <ChevronDown size={12} className={`transition-transform duration-150 ${menuOpen ? "rotate-180" : ""}`} />
      </button>

      <textarea
        ref={taRef}
        data-testid="composer-input"
        rows={1}
        value={value}
        disabled={busy}
        placeholder={busy ? "Agent working…" : "Ask about materials, or request CAD/FEA tools…"}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        className="max-h-40 min-h-[38px] flex-1 resize-none bg-transparent px-1 py-2 text-[13.5px] leading-relaxed text-ink outline-none placeholder:text-ink-faint"
      />

      <button
        type="submit"
        data-testid="send-button"
        disabled={busy || !value.trim()}
        className="inline-flex h-[38px] w-[46px] shrink-0 items-center justify-center rounded-[2px] bg-accent text-[#16130e] transition-colors duration-150 hover:bg-[#ff7a42] active:bg-accent-dim disabled:cursor-not-allowed disabled:bg-raised disabled:text-ink-faint"
        title="Send"
      >
        <SendMark size={15} />
      </button>
    </form>
  );
}

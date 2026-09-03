import { useEffect, useMemo, useRef, useState } from "react";
import type { PromptItem, PromptLibrary } from "../lib/types";
import { CostChip, Stamp } from "./primitives";
import { filterPrompts, type PickOptions } from "./PromptMenu";

/** ⌘K command palette over the same prompt library as the dropdown. */
export function CommandPalette({
  library,
  onPick,
  onClose,
}: {
  library: PromptLibrary;
  onPick: (item: PromptItem, opts: PickOptions) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const groups = useMemo(() => filterPrompts(library, query), [library, query]);
  const flat = useMemo(() => groups.flatMap((g) => g.items), [groups]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    setCursor(0);
  }, [query]);

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${cursor}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  function pickCurrent(send: boolean) {
    const item = flat[cursor];
    if (item) onPick(item, { send });
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, flat.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      pickCurrent(true);
    }
  }

  let idx = -1;
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-[12vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      data-testid="command-palette"
    >
      <div
        className="w-[min(620px,calc(100vw-2rem))] overflow-hidden rounded-[4px] border border-line-strong bg-panel shadow-[0_12px_40px_rgba(0,0,0,0.6)]"
        onKeyDown={onKeyDown}
      >
        <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
          <span className="font-mono text-[11px] text-accent">⌘K</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search prompts — Enter sends, click inserts…"
            className="w-full bg-transparent text-[13px] text-ink outline-none placeholder:text-ink-faint"
          />
        </div>
        <div ref={listRef} className="max-h-[48vh] overflow-y-auto py-1">
          {flat.length === 0 && (
            <div className="px-3 py-6 text-center font-mono text-[11px] text-ink-faint">
              Nothing matches — clear the query.
            </div>
          )}
          {groups.map(({ category, items }) => (
            <div key={category.id}>
              <div className="px-3 pt-2 pb-1 font-mono text-[10px] tracking-[0.14em] text-ink-faint uppercase">
                {category.title}
              </div>
              {items.map((item) => {
                idx += 1;
                const i = idx;
                return (
                  <button
                    key={item.id}
                    type="button"
                    data-idx={i}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      onPick(item, { send: false });
                    }}
                    onMouseEnter={() => setCursor(i)}
                    className={`flex w-full items-start gap-2 px-3 py-1.5 text-left transition-colors duration-100 ${
                      i === cursor ? "bg-raised" : ""
                    }`}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12.5px] text-ink">{item.title}</span>
                      <span className="mt-0.5 block truncate font-mono text-[10.5px] text-ink-faint">
                        {item.prompt}
                      </span>
                    </span>
                    <span className="mt-0.5 flex shrink-0 items-center gap-1">
                      {item.freecad && <Stamp kind="accent" label="freecad" />}
                      <CostChip cost={item.cost} />
                    </span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
        <div className="flex items-center gap-4 border-t border-line px-3 py-1.5 font-mono text-[10px] text-ink-faint">
          <span>↑↓ navigate</span>
          <span>↵ send now</span>
          <span>click inserts</span>
          <span className="ml-auto">esc closes</span>
        </div>
      </div>
    </div>
  );
}

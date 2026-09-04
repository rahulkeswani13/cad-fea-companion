import { useEffect, useMemo, useRef, useState } from "react";
import type { PromptCategory, PromptItem, PromptLibrary } from "../lib/types";
import { CostChip, Stamp } from "./primitives";
import { Search } from "../lib/icons";

export interface PickOptions {
  /** true = send immediately (palette Enter); false = insert into composer. */
  send?: boolean;
}

export function filterPrompts(library: PromptLibrary, query: string): { category: PromptCategory; items: PromptItem[] }[] {
  const q = query.trim().toLowerCase();
  const groups: { category: PromptCategory; items: PromptItem[] }[] = [];
  for (const category of library.categories) {
    const items = q
      ? category.items.filter(
          (it) =>
            it.title.toLowerCase().includes(q) ||
            it.prompt.toLowerCase().includes(q) ||
            category.title.toLowerCase().includes(q),
        )
      : category.items;
    if (items.length > 0) groups.push({ category, items });
  }
  return groups;
}

export function PromptRow({
  item,
  onPick,
  selected,
  onHover,
}: {
  item: PromptItem;
  onPick: (item: PromptItem, opts: PickOptions) => void;
  selected?: boolean;
  onHover?: () => void;
}) {
  return (
    <button
      type="button"
      onMouseDown={(e) => {
        e.preventDefault();
        onPick(item, { send: false });
      }}
      onMouseEnter={onHover}
      className={`flex w-full items-start gap-2 px-3 py-1.5 text-left transition-colors duration-100 ${
        selected ? "bg-raised" : "hover:bg-raised"
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
}

/** Categorized dropdown anchored to the composer's Prompts button. */
export function PromptMenu({
  library,
  onPick,
  onClose,
}: {
  library: PromptLibrary;
  onPick: (item: PromptItem, opts: PickOptions) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const groups = useMemo(() => filterPrompts(library, query), [library, query]);

  useEffect(() => {
    function onDocMouseDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div
      ref={ref}
      data-testid="prompt-menu"
      className="absolute bottom-full left-0 z-30 mb-2 w-[min(560px,calc(100vw-4rem))] overflow-hidden rounded-[4px] border border-line-strong bg-panel shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
    >
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        <Search className="text-ink-faint" size={13} />
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter the prompt library…"
          className="w-full bg-transparent font-mono text-[12px] text-ink outline-none placeholder:text-ink-faint"
        />
      </div>
      <div className="max-h-[46vh] overflow-y-auto py-1">
        {groups.length === 0 && (
          <div className="px-3 py-4 text-center font-mono text-[11px] text-ink-faint">
            No prompts match — clear the filter.
          </div>
        )}
        {groups.map(({ category, items }) => (
          <div key={category.id}>
            <div className="px-3 pt-2 pb-1 font-mono text-[10px] tracking-[0.14em] text-ink-faint uppercase">
              {category.title}
            </div>
            {items.map((item) => (
              <PromptRow key={item.id} item={item} onPick={onPick} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

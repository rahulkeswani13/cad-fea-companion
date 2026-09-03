import { useState } from "react";
import type { PromptLibrary, WalkthroughFeature } from "../lib/types";
import { CostChip, Stamp } from "./primitives";
import { Close, Walkthrough } from "../lib/icons";

/** Left rail: 01 prompt library (categorized) + 02 feature walkthroughs. */
export function RailLeft({
  library,
  onPick,
  activeFeature,
  onSelectFeature,
}: {
  library: PromptLibrary | null;
  onPick: (prompt: string) => void;
  activeFeature: string | null;
  onSelectFeature: (id: string | null) => void;
}) {
  const [openCats, setOpenCats] = useState<Record<string, boolean>>({});

  const feature = library?.features.find((f) => f.id === activeFeature) ?? null;

  return (
    <div className="flex min-h-full flex-col">
      {/* 02 walkthrough overlay takes the rail when a feature is active */}
      {feature ? (
        <section className="px-3 py-3">
          <div className="section-label pb-2">
            <span className="index">01</span>
            <span className="truncate">{feature.title}</span>
            <button
              type="button"
              onClick={() => onSelectFeature(null)}
              title="Close walkthrough"
              className="ml-auto text-ink-faint hover:text-ink"
            >
              <Close size={13} />
            </button>
          </div>
          <p className="pb-2 text-[12px] leading-relaxed text-ink-dim">{feature.blurb}</p>
          <ol className="space-y-2">
            {feature.steps.map((step, i) => (
              <li key={i} className="rounded-[4px] border border-line bg-panel" data-testid="walkthrough-step">
                <div className="flex items-center gap-2 border-b border-line px-2.5 py-1.5">
                  <span className="font-mono text-[10px] tracking-[0.12em] text-accent uppercase">
                    step {i + 1}
                  </span>
                  <span className="ml-auto flex items-center gap-1">
                    {step.freecad && <Stamp kind="accent" label="freecad" />}
                    <CostChip cost={step.cost} />
                  </span>
                </div>
                <p className="px-2.5 py-1.5 text-[12.5px] leading-relaxed text-ink">{step.title}</p>
                {step.talking_points.length > 0 && (
                  <ul className="mx-2.5 mb-1.5 space-y-1 border-l border-line pl-2">
                    {step.talking_points.map((tp, j) => (
                      <li key={j} className="text-[11.5px] leading-relaxed text-ink-faint">
                        {tp}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="px-2.5 pb-2">
                  <button
                    type="button"
                    onClick={() => onPick(step.prompt)}
                    className="w-full rounded-[2px] border border-line-strong px-2 py-1.5 font-mono text-[10.5px] tracking-[0.1em] text-ink-dim uppercase transition-colors duration-150 hover:border-accent hover:text-accent"
                  >
                    Run step
                  </button>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ) : (
        <>
          <section className="px-3 py-3">
            <div className="section-label pb-2">
              <span className="index">01</span>
              <span>Feature walkthroughs</span>
            </div>
            <div className="space-y-1" data-testid="walkthrough-list">
              {(library?.features ?? []).map((f: WalkthroughFeature) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => onSelectFeature(f.id)}
                  className="group flex w-full items-baseline gap-2 rounded-[2px] px-1.5 py-1 text-left transition-colors duration-100 hover:bg-raised"
                >
                  <span className="shrink-0 pt-px text-ink-faint group-hover:text-accent">
                    <Walkthrough size={13} />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-[12.5px] text-ink">{f.title}</span>
                    <span className="block truncate font-mono text-[10px] text-ink-faint">
                      {f.id} · {f.steps.length} steps
                    </span>
                  </span>
                </button>
              ))}
              {!library && (
                <div className="px-1.5 py-2 font-mono text-[11px] text-ink-faint">Loading library…</div>
              )}
            </div>
          </section>

          <section className="px-3 pb-6">
            <div className="section-label pb-2">
              <span className="index">02</span>
              <span>Prompt library</span>
            </div>
            <div data-testid="prompt-library">
              {(library?.categories ?? []).map((cat) => {
                const open = openCats[cat.id] ?? true;
                return (
                  <div key={cat.id} className="mb-1">
                    <button
                      type="button"
                      onClick={() => setOpenCats((m) => ({ ...m, [cat.id]: !open }))}
                      className="flex w-full items-center gap-1.5 rounded-[2px] px-1.5 py-1 text-left transition-colors duration-100 hover:bg-raised"
                    >
                      <span className={`font-mono text-[10px] text-ink-faint transition-transform duration-150 ${open ? "rotate-90" : ""}`}>
                        ▸
                      </span>
                      <span className="font-mono text-[10.5px] tracking-[0.1em] text-ink-dim uppercase">
                        {cat.title}
                      </span>
                    </button>
                    {open && (
                      <ul className="mt-0.5">
                        {cat.items.map((item) => (
                          <li key={item.id}>
                            <button
                              type="button"
                              title={item.prompt}
                              onClick={() => onPick(item.prompt)}
                              className="flex w-full items-center gap-2 rounded-[2px] py-1 pl-5 pr-1.5 text-left transition-colors duration-100 hover:bg-raised"
                            >
                              <span className="min-w-0 flex-1 truncate text-[12px] text-ink/90">
                                {item.title}
                              </span>
                              {item.freecad && <span className="h-1 w-1 shrink-0 rounded-full bg-accent" />}
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

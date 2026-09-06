import { useState } from "react";
import type { PromptLibrary } from "../lib/types";
import { JOURNEYS, resolveStepPrompt, type Journey } from "../lib/journeys";
import { Stamp } from "./primitives";
import { Close, Walkthrough } from "../lib/icons";

/** Category ids that start collapsed (the honest-failure playground). */
const COLLAPSED_CATEGORIES = new Set(["validate"]);

/** Left rail: guided journeys (frontend config, ADR-017) + the prompt
 *  library. Every selection fills the composer — only Send executes. */
export function RailLeft({
  library,
  onPick,
  activeJourney,
  onSelectJourney,
}: {
  library: PromptLibrary | null;
  onPick: (prompt: string) => void;
  activeJourney: string | null;
  onSelectJourney: (id: string | null) => void;
}) {
  const [openCats, setOpenCats] = useState<Record<string, boolean>>({});
  const [stepIdx, setStepIdx] = useState(0);

  const journey: Journey | null =
    JOURNEYS.find((j) => j.id === activeJourney) ?? null;
  const step = journey?.steps[stepIdx] ?? null;
  const stepPrompt = step ? resolveStepPrompt(step, library) : null;

  return (
    <div className="flex min-h-full flex-col">
      {journey ? (
        <section className="px-3 py-3" data-testid="journey-detail">
          <div className="section-label pb-2">
            <span className="truncate">{journey.title}</span>
            <button
              type="button"
              onClick={() => onSelectJourney(null)}
              title="Close journey"
              className="ml-auto text-ink-faint hover:text-ink"
            >
              <Close size={13} />
            </button>
          </div>

          <p className="pb-2 text-[12px] leading-relaxed text-ink-dim">
            {journey.purpose}
          </p>
          {journey.prerequisites.length > 0 && (
            <div className="mb-2 rounded-[2px] border border-line bg-raised/40 px-2 py-1.5">
              <div className="font-mono text-[9.5px] tracking-[0.12em] text-ink-faint uppercase">
                prerequisites
              </div>
              <ul className="mt-0.5 list-disc pl-4">
                {journey.prerequisites.map((p, i) => (
                  <li key={i} className="text-[11.5px] leading-relaxed text-ink-dim">
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {step && (
            <div className="rounded-[4px] border border-line bg-panel" data-testid="journey-step">
              <div className="flex items-center gap-2 border-b border-line px-2.5 py-1.5">
                <span className="font-mono text-[10px] tracking-[0.12em] text-accent uppercase">
                  step {stepIdx + 1} of {journey.steps.length}
                </span>
                <span className="ml-auto flex items-center gap-1">
                  <Stamp kind="accent" label="manual" />
                </span>
              </div>
              <p className="px-2.5 py-1.5 text-[12.5px] leading-relaxed text-ink">
                {step.title}
              </p>
              <div className="px-2.5 pb-2">
                <div className="mb-1.5 rounded-[2px] border border-line bg-raised/40 px-2 py-1.5 font-mono text-[10.5px] leading-relaxed text-ink-dim" data-testid="journey-prompt-preview">
                  {stepPrompt ?? "Library offline — prompt unavailable."}
                </div>
                <button
                  type="button"
                  disabled={!stepPrompt}
                  onClick={() => stepPrompt && onPick(stepPrompt)}
                  className="w-full rounded-[2px] border border-line-strong px-2 py-1.5 font-mono text-[10.5px] tracking-[0.1em] text-ink-dim uppercase transition-colors duration-150 hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Use prompt
                </button>
              </div>
            </div>
          )}

          <div className="mt-2 flex items-center justify-between">
            <button
              type="button"
              disabled={stepIdx === 0}
              onClick={() => setStepIdx((i) => Math.max(0, i - 1))}
              className="rounded-[2px] border border-line px-2 py-1 font-mono text-[10.5px] tracking-[0.1em] text-ink-dim uppercase transition-colors duration-150 hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
              data-testid="journey-prev"
            >
              ← Previous
            </button>
            <button
              type="button"
              disabled={stepIdx >= journey.steps.length - 1}
              onClick={() => setStepIdx((i) => Math.min(journey.steps.length - 1, i + 1))}
              className="rounded-[2px] border border-line px-2 py-1 font-mono text-[10.5px] tracking-[0.1em] text-ink-dim uppercase transition-colors duration-150 hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
              data-testid="journey-next"
            >
              Next →
            </button>
          </div>
          <p className="pt-2 font-mono text-[9.5px] leading-relaxed text-ink-faint">
            Journeys advance manually — the console never claims a step completed.
          </p>
        </section>
      ) : (
        <>
          <section className="px-3 py-3">
            <div className="section-label pb-2">
              <span>Guided journeys</span>
            </div>
            <div className="space-y-1" data-testid="journey-list">
              {JOURNEYS.map((j) => (
                <button
                  key={j.id}
                  type="button"
                  onClick={() => {
                    setStepIdx(0);
                    onSelectJourney(j.id);
                  }}
                  className="group flex w-full items-baseline gap-2 rounded-[2px] px-1.5 py-1 text-left transition-colors duration-100 hover:bg-raised"
                >
                  <span className="shrink-0 pt-px text-ink-faint group-hover:text-accent">
                    <Walkthrough size={13} />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-[12.5px] text-ink">{j.title}</span>
                    <span className="block truncate font-mono text-[10px] text-ink-faint">
                      {j.steps.length} steps · manual
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </section>

          <section className="px-3 pb-6">
            <div className="section-label pb-2">
              <span>Prompt library</span>
            </div>
            <div data-testid="prompt-library">
              {(library?.categories ?? []).map((cat) => {
                const open = openCats[cat.id] ?? !COLLAPSED_CATEGORIES.has(cat.id);
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

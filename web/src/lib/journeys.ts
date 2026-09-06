import type { PromptLibrary } from "./types";

/**
 * Customer-facing guided journeys (ADR-017, PR 2). Journeys orchestrate
 * canonical library prompts by reference — the executable text stays
 * single-sourced in data/prompts.json (ADR-015). Conversational steps may
 * carry inline text. Navigation is manual; no automatic completion claims.
 * The technical feature walkthroughs remain in data/prompts.json `features`
 * and demo/Features.md; the UI does not render them.
 */
export interface JourneyStep {
  title: string;
  /** Library item id — prompt text resolves from the library. */
  ref?: string;
  /** Inline conversational prompt (no library equivalent). */
  prompt?: string;
}

export interface Journey {
  id: string;
  title: string;
  purpose: string;
  prerequisites: string[];
  steps: JourneyStep[];
}

export const JOURNEYS: Journey[] = [
  {
    id: "j-uav-iteration",
    title: "UAV arm design iteration",
    purpose:
      "Take the flagship UAV arm from a solid web to an X-truss lattice and see what the redesign buys.",
    prerequisites: [
      "FreeCAD available for live geometry",
      "No prior session state needed",
    ],
    steps: [
      { title: "Create the solid UAV arm", ref: "cad-uav-solid" },
      { title: "Solve the 120 N thrust load", ref: "solve-uav-120n" },
      { title: "Switch to the X-truss variant", ref: "cad-uav-xtruss" },
      { title: "Re-solve the 120 N thrust load", ref: "solve-uav-120n" },
      {
        title: "Explain the differences",
        prompt:
          "Explain the differences between the solid and X-truss UAV arm results: mass, peak stress, safety factor — and state what you would still not claim without a live solve.",
      },
    ],
  },
  {
    id: "j-cantilever-checks",
    title: "Cantilever analysis checks",
    purpose:
      "Benchmark the solver against beam theory, then check that the mesh is converged.",
    prerequisites: [
      "FreeCAD available for a live solve",
      "Benchmark geometry: 100 × 20 × 5 mm beam",
    ],
    steps: [
      { title: "Create the benchmark cantilever", ref: "cad-cantilever" },
      { title: "Solve with a 100 N tip load", ref: "solve-cantilever" },
      {
        title: "Compare against beam theory",
        prompt:
          "Compare the FEA result to the analytical Euler–Bernoulli beam estimate for this cantilever: expected vs actual stress, the ratio, and what a divergence would mean.",
      },
      { title: "Run the mesh sensitivity study", ref: "solve-convergence" },
    ],
  },
  {
    id: "j-pedal-materials",
    title: "Brake pedal material comparison",
    purpose:
      "Weigh titanium against aluminum on the brake pedal, then commit the switch and re-solve.",
    prerequisites: [
      "No prior session state needed (the journey creates the part)",
      "Material table loaded with cited properties",
    ],
    steps: [
      { title: "Create the solid brake pedal", ref: "cad-pedal-solid" },
      { title: "Solve the +500 N footpad load", ref: "solve-pedal-500n" },
      { title: "Compare Ti-6Al-4V vs Al 6061-T6", ref: "var-compare-materials" },
      {
        title: "Change the material to titanium",
        prompt: "Change the brake pedal material to Ti-6Al-4V.",
      },
      { title: "Re-solve the +500 N load", ref: "solve-pedal-500n" },
    ],
  },
];

/** Welcome starters: label + library item reference. Filling the composer
 *  only — nothing executes until Send (ADR-017). */
export const STARTERS: { label: string; ref: string }[] = [
  { label: "Create a UAV arm", ref: "cad-uav-solid" },
  { label: "Create a brake pedal", ref: "cad-pedal-solid" },
  { label: "Create a cantilever beam", ref: "cad-cantilever" },
  { label: "Ask about materials", ref: "qa-material-guidance" },
];

/** Resolve a journey step's executable prompt from the library.
 *  Returns null when the reference cannot be resolved (library offline). */
export function resolveStepPrompt(
  step: { ref?: string; prompt?: string },
  library: PromptLibrary | null,
): string | null {
  if (step.prompt) return step.prompt;
  if (!step.ref || !library) return null;
  for (const cat of library.categories) {
    const item = cat.items.find((i) => i.id === step.ref);
    if (item) return item.prompt;
  }
  return null;
}

/** Resolve a starter prompt by library reference; null when unresolvable. */
export function resolveStarterPrompt(
  ref: string,
  library: PromptLibrary | null,
): string | null {
  return resolveStepPrompt({ ref }, library);
}

/** Wire types shared with companion/main.py — keep field names exact. */

export interface PromptItem {
  id: string;
  title: string;
  prompt: string;
  /** true when running it will do FreeCAD work (create/solve/open GUI). */
  freecad?: boolean;
  /** "instant" | "seconds" | "solve" — rough demo cost hint. */
  cost?: "instant" | "seconds" | "solve";
}

export interface PromptCategory {
  id: string;
  title: string;
  items: PromptItem[];
}

export interface WalkthroughStep {
  title: string;
  prompt: string;
  talking_points: string[];
  freecad?: boolean;
  cost?: PromptItem["cost"];
}

export interface WalkthroughFeature {
  id: string;
  title: string;
  blurb: string;
  steps: WalkthroughStep[];
}

export interface PromptLibrary {
  version: string;
  categories: PromptCategory[];
  features: WalkthroughFeature[];
}

export interface Citation {
  source?: string;
  text?: string;
  tfidf_rank?: number;
  bm25_rank?: number;
  score?: number;
}

export interface ToolResult {
  name: string;
  result: Record<string, unknown>;
}

export interface FinalPayload {
  type: "final";
  answer?: string;
  error?: string;
  thread_id?: string;
  citations?: Citation[];
  grounding?: "strong" | "weak" | "none";
  tool_results?: ToolResult[];
  interrupted?: boolean;
  interrupt?: unknown;
  usage?: { total_tokens?: number; turns?: number };
}

export interface HealthPayload {
  ok?: boolean;
  freecad_cmd?: string | null;
  llm?: { provider?: string; model?: string; configured?: boolean };
  agent?: { require_tool_confirm?: boolean; max_tool_rounds?: number };
  session_usage?: {
    threads?: Record<string, { total_tokens?: number; turns?: number }>;
  };
}

export interface ProgramParam {
  key: string;
  value: unknown;
}

export interface DesignProgram {
  active_part: string | null;
  part: string | null;
  rev: number | null;
  params_hash: string | null;
  params: ProgramParam[];
  programs?: { part: string; rev: number; params_hash: string }[];
  note?: string;
  error?: string;
}

export interface RunRow {
  run_id?: string;
  part?: string;
  web_type?: string;
  force_n?: number;
  method?: string;
  max_von_mises_mpa?: number;
  max_vm_location_mm?: unknown;
  safety_factor_vs_yield?: number;
  mesh_max_size_mm?: number;
  divergence_flag?: boolean;
  ts?: string;
}

export interface RunsPayload {
  part: string | null;
  runs: RunRow[];
  error?: string;
}

export interface SolverStatus {
  freecad: boolean;
  freecad_cmd: string | null;
  llm: { provider?: string; model?: string; configured?: boolean };
  require_tool_confirm: boolean;
}

export type Role = "user" | "assistant" | "status";

export interface ChatMessage {
  id: number;
  role: Role;
  text?: string;
  html?: string;
  toolResults?: ToolResult[];
  citations?: Citation[];
  grounding?: FinalPayload["grounding"];
  stamp?: "pass" | "caution" | "fail";
}

export interface InterruptState {
  toolNames: string[];
}

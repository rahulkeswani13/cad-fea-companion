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
  evidence_id?: string;
  chunk_id?: string;
  source?: string;
  section_id?: string;
  text?: string;
  tfidf_rank?: number;
  bm25_rank?: number;
  score?: number;
}

export interface RetrievalStatus {
  requested_profile?: string;
  active_profile?: string;
  fallback?: boolean;
  reason?: string;
  timing_ms?: number;
  query_rewrite?: { applied?: boolean; rules?: string[]; effective_query?: string | null };
}

/** A deterministic, citeable slice resolved from one answer evidence item. */
export interface AnswerEvidenceSpan {
  span_id?: string;
  evidence_id?: string;
  source?: string;
  text?: string;
  kind?: string;
  provenance_method?: string;
}

export interface AnswerClaim {
  text?: string;
  evidence_ids?: string[];
  /** Span IDs requested by the model; retained even when a span cannot resolve. */
  evidence_span_ids?: string[];
  /** Canonical spans resolved by the bounded evidence check. */
  evidence_spans?: AnswerEvidenceSpan[];
  /** Legacy exact-quote contract; kept for older clients and responses. */
  supporting_quotes?: { evidence_id?: string; quote?: string }[];
  structurally_supported?: boolean;
  entailment_checked?: boolean;
  issues?: string[];
}

export interface AnswerEvidence {
  status?: "supported" | "partially_supported" | "insufficient" | "check_unavailable";
  action?: "answer" | "clarify" | "refuse" | "abstain";
  checked?: boolean;
  structural_check?: string;
  semantic_check?: string;
  repair_attempted?: boolean;
  claims?: AnswerClaim[];
  gaps?: string[];
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
  retrieval?: RetrievalStatus;
  retrieval_query?: {
    query?: string;
    followup_resolved?: boolean;
    previous_user_question?: string | null;
    cad_context_used?: boolean;
  };
  answer_evidence?: AnswerEvidence;
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
  /** "runtime" (console toggle) | "setting" (AGENT_REQUIRE_TOOL_CONFIRM) */
  confirm_source?: string;
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
  retrieval?: FinalPayload["retrieval"];
  retrievalQuery?: FinalPayload["retrieval_query"];
  answerEvidence?: FinalPayload["answer_evidence"];
  stamp?: "pass" | "caution" | "fail";
}

export interface InterruptState {
  toolNames: string[];
}

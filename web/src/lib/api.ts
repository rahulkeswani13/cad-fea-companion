import type {
  DesignProgram,
  FinalPayload,
  HealthPayload,
  PromptLibrary,
  RunsPayload,
  SolverStatus,
} from "./types";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
  return (await res.json()) as T;
}

export function fetchHealth(): Promise<HealthPayload> {
  return getJson<HealthPayload>("/api/health");
}

export function fetchPrompts(): Promise<PromptLibrary> {
  return getJson<PromptLibrary>("/api/prompts");
}

export function fetchDesignProgram(part?: string): Promise<DesignProgram> {
  const q = part ? `?part=${encodeURIComponent(part)}` : "";
  return getJson<DesignProgram>(`/api/design-program${q}`);
}

export function fetchRuns(part?: string): Promise<RunsPayload> {
  const q = part ? `?part=${encodeURIComponent(part)}` : "";
  return getJson<RunsPayload>(`/api/runs${q}`);
}

export function fetchSolverStatus(): Promise<SolverStatus> {
  return getJson<SolverStatus>("/api/solver-status");
}

export interface ResumeResponse {
  answer?: string;
  error?: string;
  thread_id?: string;
  citations?: FinalPayload["citations"];
  grounding?: FinalPayload["grounding"];
  tool_results?: FinalPayload["tool_results"];
  interrupted?: boolean;
  interrupt?: unknown;
}

/** HITL resume after the operator approves/rejects a FreeCAD tool call. */
export async function resumeChat(
  threadId: string,
  approved: boolean,
): Promise<ResumeResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: "", thread_id: threadId, resume: approved }),
  });
  if (!res.ok) throw new Error(`resume → HTTP ${res.status}`);
  return (await res.json()) as ResumeResponse;
}

export type StreamEvent =
  | { type: "node"; node?: string; status?: string }
  | FinalPayload;

/**
 * Stream /api/chat/stream SSE events. The wire format is shared with the
 * legacy console: `data: {...}` frames separated by blank lines, carrying
 * `node` progress events and exactly one `final` payload.
 */
export async function streamChat(
  message: string,
  threadId: string,
  onNode: (status: string) => void,
): Promise<FinalPayload> {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId }),
  });
  if (!res.ok || !res.body) throw new Error(`stream → HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: FinalPayload | null = null;

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.trim();
      if (!line.startsWith("data:")) continue;
      const payload = JSON.parse(line.slice(5).trim()) as StreamEvent;
      if (payload.type === "node") {
        onNode(payload.status || payload.node || "Working…");
      } else if (payload.type === "final") {
        final = payload;
      }
    }
  }
  return final ?? { type: "final", answer: "No response", thread_id: threadId };
}

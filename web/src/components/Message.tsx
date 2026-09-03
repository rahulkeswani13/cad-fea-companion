import { toolSummary } from "../lib/format";
import type { ChatMessage } from "../lib/types";
import { ReportCard } from "./ReportCard";
import { Stamp } from "./primitives";

function GroundingBadge({ grounding }: { grounding?: ChatMessage["grounding"] }) {
  if (grounding === "weak")
    return <Stamp kind="caution" label="weak grounding" />;
  if (grounding === "none") return <Stamp kind="caution" label="no retrieval match" />;
  return <Stamp kind="pass" label="grounded" />;
}

function RetrievalInspector({ msg }: { msg: ChatMessage }) {
  const cites = msg.citations ?? [];
  const sources = [...new Set(cites.map((c) => c.source).filter((s): s is string => Boolean(s)))];
  return (
    <details className="mt-2 border border-line rounded-[4px] bg-raised/40">
      <summary className="cursor-pointer px-3 py-1.5 font-mono text-[10.5px] tracking-[0.1em] text-ink-dim uppercase select-none hover:text-ink">
        Retrieval inspector — {cites.length} hits
      </summary>
      <div className="border-t border-line px-3 py-2">
        {sources.length > 0 && (
          <ul className="mb-2 list-disc pl-4 text-[11.5px] text-ink-dim">
            {sources.map((s) => (
              <li key={s} className="font-mono">
                {s}
              </li>
            ))}
          </ul>
        )}
        <div className="space-y-2">
          {cites.slice(0, 4).map((c, i) => {
            const ranks = [
              c.tfidf_rank != null ? `tfidf #${c.tfidf_rank}` : null,
              c.bm25_rank != null ? `bm25 #${c.bm25_rank}` : null,
              c.score != null && c.score > 0 ? `cos ${Number(c.score).toFixed(3)}` : null,
            ]
              .filter(Boolean)
              .join(" · ");
            const text = String(c.text ?? "");
            return (
              <div key={i} className="rounded-[2px] border border-line bg-panel px-2 py-1.5">
                <div className="flex items-baseline justify-between gap-2">
                  <code className="font-mono text-[10.5px] text-caution">{c.source}</code>
                  <span className="font-mono text-[10px] text-ink-faint">{ranks}</span>
                </div>
                <p className="mt-1 line-clamp-3 text-[12px] leading-relaxed text-ink-dim">
                  {text.slice(0, 220)}
                  {text.length > 220 ? "…" : ""}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </details>
  );
}

export function Message({ msg }: { msg: ChatMessage }) {
  if (msg.role === "user") {
    return (
      <div className="pl-3" data-testid="msg-user">
        <div className="font-mono text-[10px] tracking-[0.14em] text-accent uppercase">operator</div>
        <div className="mt-1 text-[13.5px] leading-relaxed whitespace-pre-wrap text-ink">
          {msg.text}
        </div>
      </div>
    );
  }

  if (msg.role === "status") {
    return (
      <div className="flex items-center gap-2 font-mono text-[11px] text-ink-faint" data-testid="msg-status">
        <span className="caret-blink text-accent">▮</span>
        <span>{msg.text}</span>
      </div>
    );
  }

  return (
    <div className="pl-3" data-testid="msg-assistant">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] tracking-[0.14em] text-ink-faint uppercase">agent</span>
        <GroundingBadge grounding={msg.grounding} />
      </div>

      {(msg.toolResults?.length ?? 0) > 0 && (
        <div className="mt-2 space-y-2">
          {msg.toolResults!.slice(0, 6).map((tr, i) => (
            <ReportCard key={i} tr={tr} />
          ))}
        </div>
      )}

      {msg.html != null && (
        <div
          className="md-body mt-2 max-w-[72ch] text-[13.5px] leading-relaxed text-ink/95"
          dangerouslySetInnerHTML={{ __html: msg.html }}
        />
      )}

      {msg.text && !msg.html && (
        <div className="mt-2 max-w-[72ch] font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-ink-dim">
          {msg.text}
        </div>
      )}

      {(msg.citations?.length ?? 0) > 0 && <RetrievalInspector msg={msg} />}

      {!msg.html && !msg.text && (msg.toolResults?.length ?? 0) > 0 && (
        <div className="mt-1.5 font-mono text-[10.5px] text-ink-faint">
          {msg.toolResults!.map(toolSummary).join(" · ")}
        </div>
      )}
    </div>
  );
}

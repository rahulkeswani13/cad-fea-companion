import { toolSummary } from "../lib/format";
import type { ChatMessage } from "../lib/types";
import { ReportCard } from "./ReportCard";
import { Stamp } from "./primitives";

function GroundingBadge({ grounding }: { grounding?: ChatMessage["grounding"] }) {
  if (!grounding) return null;
  if (grounding === "weak")
    return <Stamp kind="caution" label="weak retrieval match" />;
  if (grounding === "none") return <Stamp kind="caution" label="no retrieval match" />;
  return <Stamp kind="pass" label="retrieval match" />;
}

function AnswerEvidenceBadge({ evidence }: { evidence?: ChatMessage["answerEvidence"] }) {
  if (!evidence?.status) return null;
  if (evidence.status === "supported") return <Stamp kind="pass" label="claims structurally supported" />;
  if (evidence.status === "partially_supported") return <Stamp kind="caution" label="partial support" />;
  if (evidence.status === "insufficient") return <Stamp kind="caution" label="insufficient evidence" />;
  return <Stamp kind="caution" label="evidence check unavailable" />;
}

/** Compact, always-visible source list (corpus paths). Full excerpts,
 *  retrieval scores and rankings live under Technical details. */
function SourcesLine({ msg }: { msg: ChatMessage }) {
  const cites = msg.citations ?? [];
  const sources = [...new Set(cites.map((c) => c.source).filter((s): s is string => Boolean(s)))];
  if (sources.length === 0) return null;
  return (
    <div className="mt-1.5 font-mono text-[10.5px] leading-relaxed text-ink-faint" data-testid="msg-sources">
      <span className="tracking-[0.1em] uppercase">sources</span>{" "}
      {sources.map((s, i) => (
        <span key={s}>
          {i > 0 && " · "}
          <span className="text-ink-dim" title={s}>
            {s}
          </span>
        </span>
      ))}
    </div>
  );
}

/** Collapsed raw evidence: tool payloads verbatim (raw tool names included)
 *  plus retrieval scores, rankings and excerpts. Nothing here is needed to
 *  read the engineering answer — that lives on the cards and Sources line. */
function TechnicalDetails({ msg }: { msg: ChatMessage }) {
  const cites = msg.citations ?? [];
  const tools = msg.toolResults ?? [];
  const retrieval = msg.retrieval;
  const evidence = msg.answerEvidence;
  if (tools.length === 0 && cites.length === 0 && !retrieval && !evidence) return null;
  return (
    <details className="mt-2 border border-line rounded-[4px] bg-raised/40" data-testid="technical-details">
      <summary className="cursor-pointer px-3 py-1.5 font-mono text-[10.5px] tracking-[0.1em] text-ink-dim uppercase select-none hover:text-ink">
        Technical details — {tools.length} payload{tools.length === 1 ? "" : "s"} · {cites.length} retrieval
        hit{cites.length === 1 ? "" : "s"}
      </summary>
      <div className="space-y-3 border-t border-line px-3 py-2">
        {retrieval && (
          <section data-testid="retrieval-status">
            <div className="pb-1 font-mono text-[9.5px] tracking-[0.12em] text-ink-faint uppercase">
              Retrieval profile
            </div>
            <div className="font-mono text-[10.5px] text-ink-dim">
              {retrieval.requested_profile ?? "unknown"} → {retrieval.active_profile ?? "unknown"}
              {retrieval.fallback ? " fallback" : ""}
              {retrieval.timing_ms != null ? ` · ${Number(retrieval.timing_ms).toFixed(2)} ms` : ""}
              {retrieval.reason ? ` · ${retrieval.reason}` : ""}
            </div>
          </section>
        )}
        {evidence && (
          <section data-testid="answer-evidence-details">
            <div className="pb-1 font-mono text-[9.5px] tracking-[0.12em] text-ink-faint uppercase">
              Answer evidence · semantic {evidence.semantic_check ?? "not reported"}
            </div>
            {(evidence.claims ?? []).map((claim, i) => (
              <div
                key={i}
                className="mb-2 font-mono text-[10.5px] text-ink-dim"
                data-testid="claim-evidence"
              >
                <div>
                  {claim.structurally_supported === false ? "removed" : "kept"} · {claim.text} · {(claim.evidence_ids ?? []).join(", ") || "no evidence"}
                </div>
                {(() => {
                  const spans = claim.evidence_spans ?? [];
                  const spanIds = [
                    ...(claim.evidence_span_ids ?? []),
                    ...spans.map((span) => span.span_id).filter((id): id is string => Boolean(id)),
                  ].filter((id, index, ids) => ids.indexOf(id) === index);
                  return (
                    <>
                      {spanIds.length > 0 && (
                        <div data-testid="claim-span-ids" className="mt-0.5 text-accent">
                          spans · {spanIds.join(", ")}
                        </div>
                      )}
                      {spans.map((span, spanIndex) => (
                        <div key={span.span_id ?? spanIndex} data-testid="evidence-span" className="mt-0.5 pl-2 text-ink-dim">
                          <span className="text-ink-faint">{span.span_id ?? "span"}</span>
                          {span.source ? ` · ${span.source}` : ""}
                          {span.kind ? ` · ${span.kind}` : ""}
                          {span.provenance_method ? ` · ${span.provenance_method}` : ""}
                          {span.text ? ` · ${span.text}` : ""}
                        </div>
                      ))}
                    </>
                  );
                })()}
                {(claim.supporting_quotes ?? []).map((quote, quoteIndex) => (
                  <div key={quoteIndex} className="mt-0.5 pl-2 text-ink-faint">
                    legacy quote · {quote.evidence_id ?? "unknown"} · {quote.quote ?? ""}
                  </div>
                ))}
              </div>
            ))}
            {(evidence.gaps ?? []).map((gap, i) => (
              <div key={i} className="font-mono text-[10.5px] text-caution">gap · {gap}</div>
            ))}
          </section>
        )}
        {tools.length > 0 && (
          <section data-testid="raw-payloads">
            <div className="pb-1 font-mono text-[9.5px] tracking-[0.12em] text-ink-faint uppercase">
              Raw tool payloads
            </div>
            <div className="space-y-1.5">
              {tools.map((tr, i) => (
                <div key={i} className="rounded-[2px] border border-line bg-panel px-2 py-1.5">
                  <code className="font-mono text-[10.5px] text-accent">{tr.name}</code>
                  <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap font-mono text-[10px] leading-relaxed text-ink-dim">
                    {JSON.stringify(tr.result, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          </section>
        )}
        {cites.length > 0 && (
          <section data-testid="retrieval-diagnostics">
            <div className="pb-1 font-mono text-[9.5px] tracking-[0.12em] text-ink-faint uppercase">
              Retrieval diagnostics
            </div>
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
          </section>
        )}
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
        <AnswerEvidenceBadge evidence={msg.answerEvidence} />
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

      <SourcesLine msg={msg} />
      <TechnicalDetails msg={msg} />

      {!msg.html && !msg.text && (msg.toolResults?.length ?? 0) > 0 && (
        <div className="mt-1.5 font-mono text-[10.5px] text-ink-faint">
          {msg.toolResults!.map(toolSummary).join(" · ")}
        </div>
      )}
    </div>
  );
}

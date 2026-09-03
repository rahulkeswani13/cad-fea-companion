import DOMPurify from "dompurify";
import { marked } from "marked";

if (marked.setOptions) {
  marked.setOptions({ breaks: true, gfm: true });
}

/** Strip simple $...$ / $$...$$ LaTeX wrappers for plain display
 *  (ported from the legacy console so both UIs render identically). */
function stripSimpleLatex(text: string): string {
  return String(text || "")
    .replace(/\$\$([\s\S]+?)\$\$/g, (_, inner: string) => inner.trim())
    .replace(/\$([^$\n]+?)\$/g, (_, inner: string) =>
      inner
        .replace(/\\text\{([^}]*)\}/g, "$1")
        .replace(/\\mathrm\{([^}]*)\}/g, "$1")
        .replace(/\\sigma_y/g, "σ_y")
        .replace(/\\rho\^?\*?/g, "ρ*")
        .replace(/\\ge/g, "≥")
        .replace(/\\leq/g, "≤")
        .replace(/\\times/g, "×")
        .replace(/\\approx/g, "≈")
        .replace(/\\nu/g, "ν")
        .replace(/\\,/g, " ")
        .replace(/[{}]/g, "")
        .trim(),
    );
}

/** Remove inline RAG citation brackets like [docs/foo.md]. */
function stripDocCitations(text: string): string {
  return String(text || "")
    .replace(/\s*\[[^\]]*\bdocs\/[^\]]*\]/gi, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/ {2,}/g, " ")
    .trim();
}

export function renderMarkdown(text: string): string {
  let cleaned = stripDocCitations(text);
  cleaned = stripSimpleLatex(cleaned);
  cleaned = cleaned
    .replace(/\\approx/g, "≈")
    .replace(/\\nu\b/g, "ν")
    .replace(/\\ge\b/g, "≥")
    .replace(/\\leq\b/g, "≤");
  const html = marked.parse(cleaned, { async: false });
  return DOMPurify.sanitize(html);
}

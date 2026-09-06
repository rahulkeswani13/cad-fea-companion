#!/usr/bin/env python3
"""Run the fixed lexical development baseline; no model/API calls or tuning."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from companion.rag.store import get_store, ingest_docs
from eval.benchmark import benchmark_hash, evaluate_evidence, load_benchmark, require_review, resolve_relevance


def run_baseline(benchmark: dict, split: str = 'development') -> dict:
    if split not in {'development', 'heldout'}:
        raise ValueError('Unknown split')
    if split == 'heldout':
        require_review(benchmark)
    store = get_store()
    if store.index_metadata.get('fingerprint') != benchmark['corpus_fingerprint']:
        raise ValueError('Corpus drift: rebuild and re-review labels before comparing metrics')
    cases = [c for c in benchmark['cases'] if c['split'] == split]
    scored = evaluate_evidence(resolve_relevance(cases, store.chunks), store.search, k=4)
    return {
        'schema_version': 1, 'benchmark_hash': benchmark_hash(benchmark),
        'corpus_fingerprint': benchmark['corpus_fingerprint'],
        'review_status': benchmark['review']['status'],
        'provisional': benchmark['review']['status'] != 'approved',
        'split': split, 'profile': 'lexical', 'query_mode': 'latest_message_only',
        'configuration': {'tfidf_max_features': 4096, 'candidates_per_retriever': 10, 'rrf_k': 60, 'final_k': 4},
        'answer_evaluation': 'not_run',
        'acceptance': 'pending_generated_answer_evaluation_and_critical_review',
        **scored,
    }


def review_markdown(benchmark: dict) -> str:
    selected = {c['id']: c for c in benchmark['cases']}
    lines = [
        '# RAG benchmark review — 20 development examples', '',
        '**Status: awaiting your review.** These are expected answers, not model outputs.', '',
        'For each example, check whether the expected behavior is useful, the facts and source',
        'passages support it, and the forbidden claims capture the important limits. Reply',
        'with case IDs and corrections, or accept all 20. No retrieval tuning has started.',
        '',
        f'Benchmark content hash: `{benchmark_hash(benchmark)}`', '',
    ]
    for index, cid in enumerate(benchmark['review_case_ids'], 1):
        case = selected[cid]
        lines += [f'## {index}. {cid} — {case["category"]}', '', f'**Question:** {case["query"]}', '']
        for turn in case['history']:
            lines += [f'Previous {turn["role"]}: {turn["content"]}', '']
        lines += [f'**Expected:** {case["expected_action"]}; evidence {case["expected_support"]}.', '', '**Required facts / behavior:**', '']
        lines += ['- ' + fact for fact in case['required_facts']]
        lines += ['', '**Must not claim:**', '']
        lines += ['- ' + fact for fact in case['forbidden_claims']] or ['- No additional forbidden claims.']
        if case['numeric_expectations']:
            lines += ['', '**Expected numbers (reference values only):**', '']
            lines += [f'- {n["name"]}: {n["value"]} {n["unit"]}; tolerance {n["tolerance"]}.' for n in case['numeric_expectations']]
        lines += ['', '**Supporting passages:**', '']
        for group in case['required_evidence']:
            for alt in group['alternatives']:
                anchor = alt['section_id'].split('::', 1)[-1]
                lines += [f'- [{alt["source"]}](../../{alt["source"]}#{anchor}) — {group["id"]}', '', '> ' + alt['quote'].replace('\n', '\n> '), '']
        if not case['required_evidence']:
            lines += ['No reference passage establishes the requested fact; clarification or abstention is expected.', '']
        lines += [f'Critical case: {"yes" if case["critical"] else "no"}.', '']
    return '\n'.join(lines).rstrip() + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['development', 'heldout'], default='development')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--review-output', type=Path)
    args = parser.parse_args()
    try:
        benchmark = load_benchmark()
        # Block held-out access before ingestion or executing queries.
        if args.split == 'heldout':
            require_review(benchmark)
        ingest = ingest_docs(reuse_if_unchanged=True)
        if not ingest['ok']:
            raise ValueError(ingest['error'])
        report = run_baseline(benchmark, args.split)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        if args.review_output:
            args.review_output.parent.mkdir(parents=True, exist_ok=True)
            args.review_output.write_text(review_markdown(benchmark), encoding='utf-8')
        print(json.dumps({k: v for k, v in report.items() if k != 'per_query'}, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(f'Benchmark not run: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

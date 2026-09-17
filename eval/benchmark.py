"""ADR-018 draft benchmark: evidence groups, split isolation and review gating.

A required group can have equivalent supporting passages. A hit must contain an
annotated quote in the annotated section; matching a document alone earns no
credit. This module evaluates retrieval only, never generated-answer quality.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / 'eval' / 'rag_benchmark.json'
CATEGORIES = {'fact', 'paraphrase', 'comparison', 'followup', 'unsupported', 'ambiguity', 'conflict', 'adversarial'}


def normalized(text: str) -> str:
    """Compare quoted content, not Markdown presentation syntax.

    Labels intentionally store readable excerpts, while the reference passages
    can use emphasis or inline-code delimiters around the same words.  Source
    and section identity remain exact; this only removes non-semantic wrapper
    characters before the required whitespace-normalized substring check.
    """
    # Underscores are meaningful in tool and parameter identifiers such as
    # ``query_results``.  Strip asterisk emphasis, but preserve identifiers.
    text = re.sub(r"(?<!\\)\*{1,3}", "", text)
    text = text.replace("`", "").replace("\\|", "|")
    return re.sub(r'\s+', ' ', text).strip()


def benchmark_hash(benchmark: dict[str, Any]) -> str:
    """Review status is excluded; changing labels or corpus invalidates approval."""
    fixture = {k: benchmark[k] for k in ('schema_version', 'corpus_fingerprint', 'review_case_ids', 'cases')}
    return hashlib.sha256(json.dumps(fixture, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_benchmark(benchmark: dict[str, Any], *, check_sources: bool = True) -> None:
    if benchmark.get('schema_version') != 1:
        raise ValueError('Unsupported benchmark schema')
    cases = benchmark.get('cases')
    if not isinstance(cases, list) or len(cases) != 100:
        raise ValueError('Benchmark requires exactly 100 cases')
    if Counter(c.get('split') for c in cases) != {'development': 70, 'heldout': 30}:
        raise ValueError('Benchmark requires 70 development and 30 held-out cases')
    if sum(c.get('critical') is True for c in cases) != 20:
        raise ValueError('Benchmark requires 20 critical cases')
    if not isinstance(benchmark.get('corpus_fingerprint'), str) or not benchmark['corpus_fingerprint']:
        raise ValueError('Missing corpus fingerprint')
    ids: set[str] = set()
    queries: set[str] = set()
    families: dict[str, str] = {}
    evidence_catalog: dict[str, list[str]] = {}
    source_text: dict[str, str] = {}
    if check_sources:
        from companion.rag.corpus import manifest_entries
        from companion.rag.chunking import chunk_text
        for entry in manifest_entries():
            source = entry['path']
            text = (ROOT / source).read_text(encoding='utf-8')
            source_text[source] = normalized(text)
            for chunk in chunk_text(text, source):
                evidence_catalog.setdefault(chunk.section_id, []).append(normalized(chunk.text))
    for case in cases:
        for field in ('id', 'family', 'query'):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError(f'Missing {field}')
        cid = case['id']
        if cid in ids:
            raise ValueError(f'Duplicate case id: {cid}')
        ids.add(cid)
        # The same follow-up wording is valid with distinct supplied history.
        identity = normalized(case['query']).casefold() + json.dumps(case.get('history'), sort_keys=True)
        if identity in queries:
            raise ValueError(f'Duplicate question: {cid}')
        queries.add(identity)
        if case['family'] in families and families[case['family']] != case['split']:
            raise ValueError(f'Family leaks across splits: {case["family"]}')
        families[case['family']] = case['split']
        if case.get('category') not in CATEGORIES:
            raise ValueError(f'Unknown category: {cid}')
        if type(case.get('critical')) is not bool:
            raise ValueError(f'Invalid critical flag: {cid}')
        if case.get('expected_action') not in {'answer', 'clarify', 'abstain'}:
            raise ValueError(f'Invalid expected action: {cid}')
        if case.get('expected_support') not in {'supported', 'partial', 'insufficient'}:
            raise ValueError(f'Invalid expected support: {cid}')
        for field in ('required_facts', 'forbidden_claims'):
            if not isinstance(case.get(field), list) or any(not isinstance(v, str) or not v.strip() for v in case[field]):
                raise ValueError(f'Invalid {field}: {cid}')
        if not case['required_facts']:
            raise ValueError(f'Missing expected behavior/facts: {cid}')
        if not isinstance(case.get('history'), list):
            raise ValueError(f'Invalid history: {cid}')
        for turn in case['history']:
            if turn.get('role') not in {'user', 'assistant'} or not isinstance(turn.get('content'), str) or not turn['content'].strip():
                raise ValueError(f'Invalid history turn: {cid}')
        if not isinstance(case.get('numeric_expectations'), list):
            raise ValueError(f'Invalid numeric expectations: {cid}')
        for number in case['numeric_expectations']:
            if (not isinstance(number.get('name'), str) or not number['name']
                    or not isinstance(number.get('unit'), str) or not number['unit']
                    or any(type(number.get(k)) not in (int, float) or not math.isfinite(number[k]) for k in ('value', 'tolerance'))
                    or number['tolerance'] < 0):
                raise ValueError(f'Invalid numeric expectation: {cid}')
        groups = case.get('required_evidence')
        if not isinstance(groups, list):
            raise ValueError(f'Invalid evidence: {cid}')
        if case['expected_support'] in {'supported', 'partial'} and not groups:
            raise ValueError(f'Answerable case lacks evidence: {cid}')
        group_ids = set()
        for group in groups:
            if not isinstance(group.get('id'), str) or not group['id'] or group['id'] in group_ids:
                raise ValueError(f'Duplicate/missing evidence group: {cid}')
            group_ids.add(group['id'])
            alternatives = group.get('alternatives')
            if not isinstance(alternatives, list) or not alternatives:
                raise ValueError(f'Empty evidence alternatives: {cid}')
            for alt in alternatives:
                if any(not isinstance(alt.get(k), str) or not alt[k].strip() for k in ('source', 'section_id', 'quote')):
                    raise ValueError(f'Incomplete passage: {cid}')
                if not alt['section_id'].startswith(alt['source'] + '::'):
                    raise ValueError(f'Passage/source mismatch: {cid}')
                quote = normalized(alt['quote'])
                if check_sources and (alt['source'] not in source_text
                        or quote not in source_text[alt['source']]
                        or not any(quote in text for text in evidence_catalog.get(alt['section_id'], []))):
                    raise ValueError(f'Unresolvable evidence in {cid}: {alt["section_id"]}: {quote[:90]}')
    review_ids = benchmark.get('review_case_ids', [])
    development = {c['id'] for c in cases if c['split'] == 'development'}
    if len(review_ids) != 20 or len(set(review_ids)) != 20 or not set(review_ids) <= development:
        raise ValueError('Review requires 20 distinct development cases')
    review = benchmark.get('review') or {}
    if review.get('status') not in {'pending', 'approved'}:
        raise ValueError('Invalid review status')
    if review['status'] == 'approved' and review.get('benchmark_hash') != benchmark_hash(benchmark):
        raise ValueError('Review approval does not match current labels/corpus')


def load_benchmark(path: Path | None = None) -> dict[str, Any]:
    data = json.loads((path or DEFAULT_PATH).read_text(encoding='utf-8'))
    validate_benchmark(data)
    return data


def require_review(benchmark: dict[str, Any]) -> None:
    review = benchmark.get('review') or {}
    if review.get('status') != 'approved' or review.get('benchmark_hash') != benchmark_hash(benchmark):
        raise ValueError('User benchmark review is pending; tuning and held-out evaluation are blocked')


def _matches(hit: dict[str, Any], alternative: dict[str, Any]) -> bool:
    return (hit.get('source') == alternative['source']
            and hit.get('section_id') == alternative['section_id']
            and normalized(alternative['quote']) in normalized(str(hit.get('text', ''))))


def evaluate_evidence(cases: list[dict[str, Any]], retrieve_fn: Callable, k: int = 4) -> dict[str, Any]:
    """Binary passage precision/nDCG and required-group recall, macro averaged.

    Duplicate hits cannot earn extra credit. Missing result slots are irrelevant.
    No-evidence cases are preserved with null retrieval scores, never free passes.
    nDCG uses annotated retrievable chunks as relevant documents, not a guessed
    number of relevant source files. A chunk satisfying several groups is one hit.
    """
    if k < 1:
        raise ValueError('k must be positive')
    rows = []
    for case in cases:
        hits = (retrieve_fn(case['query'], k) or [])[:k]
        groups = case['required_evidence']
        found: set[str] = set()
        ranked_gains = []
        seen_hits = set()
        for hit in hits:
            key = (hit.get('source'), hit.get('section_id'), hit.get('chunk_id') or normalized(str(hit.get('text', ''))))
            matched = {g['id'] for g in groups if any(_matches(hit, alt) for alt in g['alternatives'])}
            gain = int(bool(matched) and key not in seen_hits)
            ranked_gains.append(gain)
            seen_hits.add(key)
            found.update(matched)
        dcg = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(ranked_gains))
        # Gold relevant-passage count is supplied by the runner's corpus census.
        relevant_count = case.get('relevant_chunk_count')
        if groups and relevant_count is None:
            raise ValueError('Resolve relevant_chunk_count from the corpus before scoring')
        ideal = sum(1 / math.log2(rank + 2) for rank in range(min(k, relevant_count or 0))) if groups else 0
        rows.append({
            'id': case['id'], 'category': case['category'], 'critical': case['critical'],
            'expected_action': case['expected_action'], 'expected_support': case['expected_support'],
            'evidence_recall': len(found) / len(groups) if groups else None,
            'precision': sum(ranked_gains) / k if groups else None,
            'ndcg': dcg / ideal if ideal else None,
            'found_evidence': sorted(found), 'missing_evidence': [g['id'] for g in groups if g['id'] not in found],
            'retrieved': [{key: hit.get(key) for key in ('source', 'section_id', 'chunk_id')} for hit in hits],
            'answer_evaluation': 'not_run',
        })
    def mean(selected, field):
        values = [r[field] for r in selected if r[field] is not None]
        return round(sum(values) / len(values), 4) if values else None
    return {
        'queries': len(rows), 'k': k,
        'scored_queries': sum(r['evidence_recall'] is not None for r in rows),
        'unscored_no_evidence': sum(r['evidence_recall'] is None for r in rows),
        'evidence_recall_at_k': mean(rows, 'evidence_recall'),
        'answerable_evidence_recall_at_k': mean([r for r in rows if r['expected_support'] in {'supported', 'partial'}], 'evidence_recall'),
        'precision_at_k': mean(rows, 'precision'), 'ndcg_at_k': mean(rows, 'ndcg'),
        'by_category': {category: {'queries': sum(r['category'] == category for r in rows),
            'evidence_recall_at_k': mean([r for r in rows if r['category'] == category], 'evidence_recall')}
            for category in sorted({r['category'] for r in rows})},
        'per_query': rows,
    }


def resolve_relevance(cases: list[dict[str, Any]], chunks: list[Any]) -> list[dict[str, Any]]:
    hits = [{'source': c.source, 'section_id': c.section_id, 'text': c.text, 'chunk_id': c.chunk_id} for c in chunks]
    return [{**case, 'relevant_chunk_count': sum(any(_matches(hit, alt) for g in case['required_evidence'] for alt in g['alternatives']) for hit in hits)} for case in cases]

"""Passage-level metrics must not inherit document-hit false positives."""
from copy import deepcopy

import pytest

from companion.rag.chunking import Chunk
from eval.benchmark import benchmark_hash, evaluate_evidence, load_benchmark, require_review, resolve_relevance, validate_benchmark


def case(groups=None):
    return {'id': 'probe', 'category': 'fact', 'critical': False,
            'expected_action': 'answer', 'expected_support': 'supported', 'query': 'yield?',
            'required_evidence': groups if groups is not None else [group('yield')],
            'relevant_chunk_count': 1}


def group(gid):
    return {'id': gid, 'alternatives': [{'source': 'a.md', 'section_id': 'a.md::steel', 'quote': gid}]}


def hit(text='yield', section='a.md::steel', cid='one'):
    return {'source': 'a.md', 'section_id': section, 'chunk_id': cid, 'text': text}


def score(item, hits):
    return evaluate_evidence([item], lambda q, k: hits, k=4)


def test_right_document_wrong_section_or_missing_quote_gets_no_credit():
    for hits in ([hit(section='a.md::other')], [hit(text='unrelated material')]):
        result = score(case(), hits)
        assert result['evidence_recall_at_k'] == 0
        assert result['ndcg_at_k'] == 0


def test_group_recall_requires_all_requested_facts():
    result = score(case([group('yield'), group('density')]), [hit()])
    assert result['evidence_recall_at_k'] == 0.5
    assert result['precision_at_k'] == 0.25
    assert result['per_query'][0]['missing_evidence'] == ['density']


def test_one_passage_can_support_multiple_groups():
    result = score(case([group('yield'), group('density')]), [hit('yield and density')])
    assert result['evidence_recall_at_k'] == 1
    assert result['ndcg_at_k'] == 1
    assert result['precision_at_k'] == 0.25


def test_duplicate_passage_does_not_inflate_precision_or_ndcg():
    result = score(case(), [hit(), hit(), hit()])
    assert result['precision_at_k'] == 0.25
    assert result['ndcg_at_k'] == 1


def test_rank_and_missing_slots_are_counted():
    result = score(case(), [hit('noise', cid='zero'), hit()])
    assert result['evidence_recall_at_k'] == 1
    assert result['ndcg_at_k'] == round(1 / __import__('math').log2(3), 4)
    assert result['precision_at_k'] == 0.25


def test_equivalent_alternative_can_satisfy_group():
    item = case()
    item['required_evidence'][0]['alternatives'].append({'source': 'b.md', 'section_id': 'b.md::s', 'quote': 'strength'})
    result = score(item, [{'source': 'b.md', 'section_id': 'b.md::s', 'text': 'strength'}])
    assert result['evidence_recall_at_k'] == 1


def test_unanswerable_case_is_preserved_not_scored_as_passing():
    item = {**case([]), 'expected_action': 'abstain', 'expected_support': 'insufficient'}
    result = score(item, [hit()])
    assert result['queries'] == 1 and result['unscored_no_evidence'] == 1
    assert result['evidence_recall_at_k'] is None
    assert result['ndcg_at_k'] is None
    assert result['per_query'][0]['answer_evaluation'] == 'not_run'


def test_gold_relevant_count_is_from_corpus_not_retrieved_results():
    chunks = [Chunk('one', 'a.md', 'yield', section_id='a.md::steel'),
              Chunk('two', 'a.md', 'yield and units', section_id='a.md::steel')]
    item = resolve_relevance([case()], chunks)[0]
    assert item['relevant_chunk_count'] == 2
    result = score(item, [hit()])
    assert result['evidence_recall_at_k'] == 1
    assert 0 < result['ndcg_at_k'] < 1


def test_real_fixture_is_resolvable_and_pending_user_review():
    benchmark = load_benchmark()
    assert benchmark['review']['status'] in {'pending', 'approved'}
    benchmark['review'] = {'status': 'pending'}
    with pytest.raises(ValueError, match='review is pending'):
        require_review(benchmark)


def test_approval_is_invalidated_by_label_changes():
    benchmark = deepcopy(load_benchmark())
    benchmark['review'] = {'status': 'approved', 'benchmark_hash': benchmark_hash(benchmark)}
    require_review(benchmark)
    benchmark['cases'][0]['query'] += ' changed'
    with pytest.raises(ValueError, match='review is pending'):
        require_review(benchmark)


def test_cross_split_family_leakage_and_bad_quotes_rejected():
    benchmark = deepcopy(load_benchmark())
    development = next(c for c in benchmark['cases'] if c['split'] == 'development')
    heldout = next(c for c in benchmark['cases'] if c['split'] == 'heldout')
    heldout['family'] = development['family']
    with pytest.raises(ValueError, match='Family leaks'):
        validate_benchmark(benchmark)
    benchmark = deepcopy(load_benchmark())
    supported = next(c for c in benchmark['cases'] if c['required_evidence'])
    supported['required_evidence'][0]['alternatives'][0]['quote'] = 'fabricated passage that does not exist'
    with pytest.raises(ValueError, match='Unresolvable evidence'):
        validate_benchmark(benchmark)


def test_heldout_runner_blocks_before_retrieval(monkeypatch):
    from eval import run_rag_benchmark as runner
    monkeypatch.setattr(runner, 'get_store', lambda: pytest.fail('must not load store for unapproved heldout'))
    with pytest.raises(ValueError, match='review is pending'):
        benchmark = {**load_benchmark(), 'review': {'status': 'pending'}}
        runner.run_baseline(benchmark, split='heldout')


def test_numeric_nan_and_invalid_review_selection_rejected():
    benchmark = deepcopy(load_benchmark())
    benchmark['cases'][0]['numeric_expectations'] = [{'name': 'bad', 'value': float('nan'), 'unit': 'MPa', 'tolerance': 0}]
    with pytest.raises(ValueError, match='numeric'):
        validate_benchmark(benchmark, check_sources=False)
    benchmark = deepcopy(load_benchmark())
    benchmark['review_case_ids'] = [benchmark['review_case_ids'][0]] * 20
    with pytest.raises(ValueError, match='20 distinct'):
        validate_benchmark(benchmark, check_sources=False)


def test_history_preserves_benchmark_identity_and_pending_status():
    from eval.history import summarize_for_history
    report = {'evidence_retrieval': {'benchmark_hash': 'abc', 'review_status': 'pending',
                                   'evidence_recall_at_k': 0.5, 'answer_evaluation': 'not_run'}}
    entry = summarize_for_history(report)
    assert entry['evidence_retrieval']['benchmark_hash'] == 'abc'
    assert entry['evidence_retrieval']['review_status'] == 'pending'
    assert entry['evidence_retrieval']['answer_evaluation'] == 'not_run'

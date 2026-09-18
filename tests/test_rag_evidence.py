from __future__ import annotations

import json

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from companion.agent.graph import build_graph, run_agent
from companion.llm.providers import AgentTurn
from companion.rag.evidence import (
    assess_structured_draft,
    check_and_repair,
    evidence_catalog,
    resolve_retrieval_query,
)
from tests.fakes import ScriptedLLMProvider, StubTools


def _catalog():
    return evidence_catalog(
        [{
            "chunk_id": "materials::steel::1",
            "source": "materials.md",
            "section_id": "materials.md::steel",
            "text": "Mild steel typical yield is 250 MPa.",
            "metadata": {
                "authority": "maintained reference",
                "applicability": "teaching values",
            },
        }],
        [],
    )


def test_followup_query_uses_one_prior_question_and_cad_context():
    resolved = resolve_retrieval_query(
        "What about titanium?",
        [
            HumanMessage(content="What is the aluminum yield value?"),
            HumanMessage(content="What about titanium?"),
        ],
        {"part": "brake_pedal", "material_id": "al6061t6"},
    )
    assert resolved["followup_resolved"] is True
    assert "Previous user question" in resolved["query"]
    assert "part=brake_pedal" in resolved["query"]


def test_standalone_query_does_not_pull_previous_question():
    resolved = resolve_retrieval_query(
        "Explain the mesh convergence procedure for the cantilever.",
        [HumanMessage(content="What is the aluminum yield value?")],
    )
    assert resolved["followup_resolved"] is False
    assert "Previous user question" not in resolved["query"]


def test_supported_structured_claim_requires_exact_quote():
    draft = """{"action":"answer","claims":[{"text":"The teaching value is 250 MPa.","evidence_ids":["D1"],"supporting_quotes":[{"evidence_id":"D1","quote":"Mild steel typical yield is 250 MPa."}]}],"gaps":[],"answer":""}"""
    result = assess_structured_draft(draft, _catalog())
    assert result["status"] == "supported"
    assert result["answer"] == "The teaching value is 250 MPa."
    assert result["claims"][0]["structurally_supported"] is True
    assert result["claims"][0]["entailment_checked"] is False
    assert result["semantic_check"] == "pending_manual_or_judge"


def test_catalog_exposes_readable_prose_table_and_tool_spans():
    catalog = evidence_catalog(
        [{
            "chunk_id": "materials::summary::1",
            "source": "materials.md",
            "section_id": "materials.md::summary",
            "text": (
                "Reference values follow.\n\n"
                "| Material | Yield |\n"
                "|---|---:|\n"
                "| Al 6061-T6 | 276 MPa |\n"
            ),
            "metadata": {"authority": "maintained reference"},
        }],
        [{
            "name": "apply_load_and_solve",
            "result": {"ok": True, "method": "calculix", "mesh": {"max_mm": 3.5}},
        }],
    )

    document = catalog[0]
    tool = catalog[1]
    assert [span["span_id"] for span in document["spans"]] == ["D1:S1", "D1:S2"]
    assert document["spans"][0]["text"] == "Reference values follow."
    assert "| Material | Yield |" in document["spans"][1]["text"]
    assert "| Al 6061-T6 | 276 MPa |" in document["spans"][1]["text"]
    assert [span["text"] for span in tool["spans"]] == [
        "$.mesh.max_mm = 3.5",
        '$.method = "calculix"',
        "$.ok = true",
    ]


def test_catalog_segments_lowercase_sentence_starts_and_cad_fields():
    catalog = evidence_catalog(
        [{
            "chunk_id": "notes::1",
            "source": "notes.md",
            "section_id": "notes.md::scope",
            "text": "First sentence. second sentence.",
            "metadata": {},
        }],
        [],
        cad_state={"geometry": {"part": "uav_arm"}, "results": None},
    )

    cad, document = catalog
    assert [span["text"] for span in cad["spans"]] == [
        '$.geometry.part = "uav_arm"',
        "$.results = null",
    ]
    assert [span["text"] for span in document["spans"]] == [
        "First sentence.",
        "second sentence.",
    ]


def test_structured_spans_are_bounded_stable_and_allow_empty_evidence():
    large_result = {"payload": "x" * 2500, "tail": 7}
    first = evidence_catalog([], [{"name": "large", "result": large_result}])[0]
    second = evidence_catalog([], [{"name": "large", "result": large_result}])[0]
    empty_document = evidence_catalog(
        [{"chunk_id": "empty", "source": "empty.md", "text": "", "metadata": {}}],
        [],
    )[0]
    empty_tool = evidence_catalog([], [{"name": "empty", "result": {}}])[0]

    assert first["spans"] == second["spans"]
    assert sum(len(span["text"]) for span in first["spans"]) <= 2000
    assert [span["span_id"] for span in first["spans"]] == ["T1:S1"]
    assert empty_document["spans"] == []
    assert empty_tool["spans"] == []


def test_span_citation_resolves_canonical_source_text_without_copied_quote():
    span_id = _catalog()[0]["spans"][0]["span_id"]
    draft = json.dumps({
        "action": "answer",
        "claims": [{
            "text": "The teaching value is 250 MPa.",
            "evidence_span_ids": [span_id],
        }],
        "gaps": [],
        "answer": "",
    })

    result = assess_structured_draft(draft, _catalog())

    claim = result["claims"][0]
    assert result["status"] == "supported"
    assert claim["evidence_ids"] == ["D1"]
    assert claim["evidence_span_ids"] == ["D1:S1"]
    assert claim["provenance_method"] == "span"
    assert claim["evidence_spans"] == [{
        "span_id": "D1:S1",
        "evidence_id": "D1",
        "source": "materials.md",
        "text": "Mild steel typical yield is 250 MPa.",
        "kind": "sentence",
        "provenance_method": "span",
    }]


def test_unknown_span_and_number_outside_cited_span_reject_claim():
    catalog = evidence_catalog(
        [{
            "chunk_id": "materials::steel::1",
            "source": "materials.md",
            "section_id": "materials.md::steel",
            "text": "Steel yield is 250 MPa. Aluminum yield is 276 MPa.",
            "metadata": {},
        }],
        [],
    )
    draft = json.dumps({
        "action": "answer",
        "claims": [
            {"text": "Aluminum yield is 276 MPa.", "evidence_span_ids": ["D1:S1"]},
            {"text": "Steel yield is 250 MPa.", "evidence_span_ids": ["D1:S99"]},
        ],
        "gaps": [],
        "answer": "",
    })

    result = assess_structured_draft(draft, catalog)

    assert result["status"] == "insufficient"
    assert any("numbers are absent" in issue for issue in result["claims"][0]["issues"])
    assert any("unknown evidence span IDs" in issue for issue in result["claims"][1]["issues"])


def test_legacy_quote_tolerates_formatting_but_not_paraphrase():
    formatted = """{"action":"answer","claims":[{"text":"The teaching value is 250 MPa.","evidence_ids":["D1"],"supporting_quotes":[{"evidence_id":"D1","quote":"Mild steel — typical yield is: 250 MPa"}]}],"gaps":[],"answer":""}"""
    paraphrased = """{"action":"answer","claims":[{"text":"The teaching value is 250 MPa.","evidence_ids":["D1"],"supporting_quotes":[{"evidence_id":"D1","quote":"Typical steel strength equals 250 MPa"}]}],"gaps":[],"answer":""}"""

    formatted_result = assess_structured_draft(formatted, _catalog())
    paraphrased_result = assess_structured_draft(paraphrased, _catalog())

    assert formatted_result["status"] == "supported"
    assert formatted_result["claims"][0]["provenance_method"] == "normalized_quote"
    assert paraphrased_result["status"] == "insufficient"


def test_legacy_normalization_preserves_comparison_operators():
    catalog = evidence_catalog(
        [{
            "chunk_id": "limits::1",
            "source": "limits.md",
            "section_id": "limits.md::mesh",
            "text": "The mesh limit must be >= 5 mm.",
            "metadata": {},
        }],
        [],
    )
    draft = """{"action":"answer","claims":[{"text":"The mesh limit must be at most 5 mm.","evidence_ids":["D1"],"supporting_quotes":[{"evidence_id":"D1","quote":"The mesh limit must be <= 5 mm"}]}],"gaps":[],"answer":""}"""

    result = assess_structured_draft(draft, catalog)

    assert result["status"] == "insufficient"
    assert any("does not match source formatting" in gap for gap in result["gaps"])


def test_legacy_normalization_preserves_unicode_comparison_operators():
    catalog = evidence_catalog(
        [{
            "chunk_id": "limits::1",
            "source": "limits.md",
            "section_id": "limits.md::mesh",
            "text": "The mesh limit must be ≥ 5 mm.",
            "metadata": {},
        }],
        [],
    )
    wrong = """{"action":"answer","claims":[{"text":"The mesh limit is 5 mm.","evidence_ids":["D1"],"supporting_quotes":[{"evidence_id":"D1","quote":"The mesh limit must be ≤ 5 mm"}]}],"gaps":[],"answer":""}"""
    equivalent = """{"action":"answer","claims":[{"text":"The mesh limit is 5 mm.","evidence_ids":["D1"],"supporting_quotes":[{"evidence_id":"D1","quote":"The mesh limit must be >= 5 mm"}]}],"gaps":[],"answer":""}"""

    assert assess_structured_draft(wrong, catalog)["status"] == "insufficient"
    assert assess_structured_draft(equivalent, catalog)["status"] == "supported"


def test_legacy_quote_crossing_sentences_resolves_each_canonical_span():
    catalog = evidence_catalog(
        [{
            "chunk_id": "notes::1",
            "source": "notes.md",
            "section_id": "notes.md::scope",
            "text": "The value is provisional. Testing is still required.",
            "metadata": {},
        }],
        [],
    )
    draft = """{"action":"answer","claims":[{"text":"The value is provisional and testing is required.","evidence_ids":["D1"],"supporting_quotes":[{"evidence_id":"D1","quote":"The value is provisional. Testing is still required."}]}],"gaps":[],"answer":""}"""

    result = assess_structured_draft(draft, catalog)

    assert result["status"] == "supported"
    assert [span["span_id"] for span in result["claims"][0]["evidence_spans"]] == [
        "D1:S1",
        "D1:S2",
    ]


def test_repair_preserves_supported_claim_and_replaces_only_failed_claim():
    catalog = _catalog()
    draft = json.dumps({
        "action": "answer",
        "claims": [
            {
                "text": "The teaching value is 250 MPa.",
                "evidence_span_ids": ["D1:S1"],
            },
            {
                "text": "The design is certified for flight.",
                "evidence_span_ids": ["D1:S99"],
            },
        ],
        "gaps": [],
        "answer": "",
    })
    repair_calls = []

    def complete(_system: str, prompt: str) -> str:
        repair_calls.append(prompt)
        return json.dumps({
            "action": "answer",
            "claims": [{
                "text": "The source provides a teaching value, not certification.",
                "evidence_span_ids": ["D1:S1"],
            }],
            "gaps": [],
            "answer": "",
        })

    answer, assessment = check_and_repair(complete, "Is it certified?", draft, catalog)

    assert len(repair_calls) == 1
    assert "The teaching value is 250 MPa." not in repair_calls[0]
    assert [claim["text"] for claim in assessment["claims"]] == [
        "The teaching value is 250 MPa.",
        "The source provides a teaching value, not certification.",
    ]
    assert answer.startswith("The teaching value is 250 MPa.")
    assert assessment["status"] == "supported"
    assert assessment["repair_attempted"] is True


def test_failed_repair_keeps_supported_partial_answer():
    catalog = _catalog()
    draft = json.dumps({
        "action": "answer",
        "claims": [
            {"text": "The teaching value is 250 MPa.", "evidence_span_ids": ["D1:S1"]},
            {"text": "The design is certified.", "evidence_span_ids": ["D1:S99"]},
        ],
        "gaps": [],
        "answer": "",
    })

    answer, assessment = check_and_repair(
        lambda _system, _prompt: "not valid JSON",
        "Is it certified?",
        draft,
        catalog,
    )

    assert assessment["status"] == "partially_supported"
    assert assessment["repair_attempted"] is True
    assert answer.startswith("The teaching value is 250 MPa.")
    assert "The design is certified." not in answer
    assert "repair response could not be checked" in assessment["gaps"]


def test_repair_ids_put_a_subset_back_in_its_original_position():
    catalog = _catalog()
    draft = json.dumps({
        "action": "answer",
        "claims": [
            {"text": "Unsupported first.", "evidence_span_ids": ["D1:S99"]},
            {"text": "The teaching value is 250 MPa.", "evidence_span_ids": ["D1:S1"]},
            {"text": "Unsupported third.", "evidence_span_ids": ["D1:S98"]},
        ],
        "gaps": [],
        "answer": "",
    })

    def complete(_system: str, prompt: str) -> str:
        assert '"repair_id": "R1"' in prompt
        assert '"repair_id": "R2"' in prompt
        return json.dumps({
            "action": "answer",
            "claims": [{
                "repair_id": "R2",
                "text": "The source is a teaching reference.",
                "evidence_span_ids": ["D1:S1"],
            }],
            "gaps": [],
            "answer": "",
        })

    answer, assessment = check_and_repair(complete, "Question", draft, catalog)

    assert [claim["text"] for claim in assessment["claims"]] == [
        "Unsupported first.",
        "The teaching value is 250 MPa.",
        "The source is a teaching reference.",
    ]
    assert "Unsupported first." not in answer
    assert answer.endswith("The source is a teaching reference.\n\nEvidence gaps: unknown evidence span IDs: D1:S99")


def test_declared_gap_without_failed_claim_does_not_spend_repair_call():
    catalog = _catalog()
    draft = json.dumps({
        "action": "answer",
        "claims": [{
            "text": "The teaching value is 250 MPa.",
            "evidence_span_ids": ["D1:S1"],
        }],
        "gaps": ["Fatigue evidence is unavailable."],
        "answer": "",
    })

    def complete(_system: str, _prompt: str) -> str:
        raise AssertionError("repair must not run when no claim failed")

    answer, assessment = check_and_repair(complete, "Question", draft, catalog)

    assert assessment["status"] == "partially_supported"
    assert assessment["repair_attempted"] is False
    assert "Fatigue evidence is unavailable." in answer


def test_numeric_claim_absent_from_evidence_is_not_rendered():
    draft = """{"action":"answer","claims":[{"text":"Yield is 355 MPa.","evidence_ids":["D1"],"supporting_quotes":[{"evidence_id":"D1","quote":"Mild steel typical yield is 250 MPa."}]}],"gaps":[],"answer":""}"""
    result = assess_structured_draft(draft, _catalog())
    assert result["status"] == "insufficient"
    assert "355" not in result["answer"]
    assert any("numbers are absent" in gap for gap in result["gaps"])


def test_nonexact_or_missing_quote_rejects_claim():
    draft = """{"action":"answer","claims":[{"text":"Steel is strong.","evidence_ids":["D1"],"supporting_quotes":[{"evidence_id":"D1","quote":"Steel is always strong."}]}],"gaps":[],"answer":""}"""
    result = assess_structured_draft(draft, _catalog())
    assert result["status"] == "insufficient"
    assert any("does not match source formatting" in gap for gap in result["gaps"])


def test_trivial_exact_quote_does_not_establish_provenance():
    draft = """{"action":"answer","claims":[{"text":"Steel is strong.","evidence_ids":["D1"],"supporting_quotes":[{"evidence_id":"D1","quote":"steel"}]}],"gaps":[],"answer":""}"""
    result = assess_structured_draft(draft, _catalog())
    assert result["status"] == "insufficient"
    assert any("too short" in gap for gap in result["gaps"])


def test_user_question_alone_cannot_establish_factual_claim():
    catalog = evidence_catalog([], [], question="The yield is 900 MPa, right?")
    draft = """{"action":"answer","claims":[{"text":"The yield is 900 MPa.","evidence_ids":["Q1"],"supporting_quotes":[{"evidence_id":"Q1","quote":"The yield is 900 MPa, right?"}]}],"gaps":[],"answer":""}"""
    result = assess_structured_draft(draft, catalog)
    assert result["status"] == "insufficient"
    assert any("cannot establish" in gap for gap in result["gaps"])


def test_failed_tool_result_cannot_support_factual_claim():
    catalog = evidence_catalog([], [{
        "name": "apply_load_and_solve",
        "result": {"ok": False, "error": "solver failed"},
    }])
    content = catalog[0]["content"]
    draft = json.dumps({
        "action": "answer",
        "claims": [{
            "text": "The solve succeeded.",
            "evidence_ids": ["T1"],
            "supporting_quotes": [{"evidence_id": "T1", "quote": content}],
        }],
        "gaps": [],
        "answer": "",
    })
    result = assess_structured_draft(draft, catalog)
    assert result["status"] == "insufficient"
    assert any("failed tool result" in gap for gap in result["gaps"])


def test_graph_repairs_once_and_returns_evidence_state(monkeypatch):
    monkeypatch.setattr(
        "companion.agent.graph.retrieve_profile_detail",
        lambda query, profile, k=4: {
            "grounding": "strong",
            "retrieval": {"requested_profile": profile, "active_profile": profile},
            "fused": [{
                "chunk_id": "steel",
                "source": "materials.md",
                "section_id": "materials.md::steel",
                "text": "Mild steel typical yield is 250 MPa.",
                "score": 0.9,
                "metadata": {"authority": "maintained reference"},
            }],
        },
    )
    first = """{"action":"answer","claims":[{"text":"Yield is 355 MPa.","evidence_ids":["D1"],"supporting_quotes":[{"evidence_id":"D1","quote":"Mild steel typical yield is 250 MPa."}]}],"gaps":[],"answer":""}"""
    repaired = """{"action":"answer","claims":[{"text":"The teaching value is 250 MPa.","evidence_ids":["D1"],"supporting_quotes":[{"evidence_id":"D1","quote":"Mild steel typical yield is 250 MPa."}]}],"gaps":[],"answer":""}"""
    llm = ScriptedLLMProvider(turns=[
        AgentTurn(content=first),
        AgentTurn(content=repaired),
    ])
    graph = build_graph(
        llm=llm,
        call_tool_fn=StubTools(),
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
    )
    result = run_agent("What is mild steel yield?", thread_id="evidence-repair", graph=graph)
    assert result["answer"] == "The teaching value is 250 MPa."
    assert result["answer_evidence"]["status"] == "supported"
    assert result["answer_evidence"]["repair_attempted"] is True
    assert len(llm.calls) == 2


def test_plain_draft_is_explicitly_unverified(monkeypatch):
    monkeypatch.setattr(
        "companion.agent.graph.retrieve_profile_detail",
        lambda query, profile, k=4: {
            "grounding": "none",
            "retrieval": {},
            "fused": [],
        },
    )
    graph = build_graph(
        llm=ScriptedLLMProvider(turns=[AgentTurn(content="A plain answer.")]),
        call_tool_fn=StubTools(),
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
    )
    result = run_agent("Question", thread_id="unchecked", graph=graph)
    assert result["answer_evidence"]["status"] == "check_unavailable"
    assert result["answer"] == "A plain answer."
    assert result["answer_evidence"]["checked"] is False

from __future__ import annotations

from companion.rag.chunking import Chunk, chunk_text


def test_legacy_chunk_constructor_and_blank_text():
    chunk = Chunk("legacy-id", "docs/example.md", "body")
    assert chunk.section_id == ""
    assert chunk.metadata == {}
    assert chunk_text("", "docs/example.md") == []
    assert chunk_text(" \n\t", "docs/example.md") == []


def test_sections_have_stable_ids_and_truthful_boundaries():
    text = "# Intro\n\nOne paragraph.\n\n## Loads\n\nLoad notes.\n\n## Loads\n\nSecond notes."
    first = chunk_text(text, "docs/reference/example.md", max_chars=800)
    second = chunk_text(text, "docs/reference/example.md", max_chars=800)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert [chunk.section_id for chunk in first] == [
        "docs/reference/example.md::intro",
        "docs/reference/example.md::loads",
        "docs/reference/example.md::loads-2",
    ]
    assert first[0].heading == "Intro"
    assert (first[0].start_line, first[0].end_line) == (1, 3)
    assert first[1].text.startswith("## Loads")
    assert (first[1].start_line, first[1].end_line) == (5, 7)


def test_tables_repeat_header_and_keep_rows_indivisible():
    text = (
        "# Values\n\n"
        "| Material | Formula |\n"
        "|---|---|\n"
        "| Al | E = 69 GPa |\n"
        "| Ti | E = 113.8 GPa |"
    )
    chunks = chunk_text(text, "docs/materials.md", max_chars=48)

    assert len(chunks) == 2
    assert all(chunk.heading == "Values" for chunk in chunks)
    assert all("| Material | Formula |" in chunk.text for chunk in chunks)
    assert all("|---|---|" in chunk.text for chunk in chunks)
    assert "| Al | E = 69 GPa |" in chunks[0].text
    assert "| Ti | E = 113.8 GPa |" in chunks[1].text
    assert chunks[0].start_line == 1 and chunks[0].end_line == 5
    assert chunks[1].start_line == 1 and chunks[1].end_line == 6


def test_long_paragraph_splits_on_boundaries_without_losing_text():
    paragraph = "First sentence stays whole. Second sentence has several words."
    chunks = chunk_text(paragraph, "docs/notes.md", max_chars=30)
    pieces = [chunk.text for chunk in chunks]

    assert len(pieces) > 1
    assert "".join(pieces) == paragraph
    assert all(chunk.start_line == 1 and chunk.end_line == 1 for chunk in chunks)


def test_scope_caveat_is_repeated_verbatim_and_provenance_is_recorded():
    caveat = "**Scope caveat:** bulk values are not verified for fatigue."
    text = f"# Materials\n\n{caveat}\n\n## Al\n\nE is 69 GPa."
    chunks = chunk_text(text, "docs/materials.md")

    assert all(caveat in chunk.text for chunk in chunks)
    assert chunks[-1].metadata["scope_caveats"] == [caveat]
    assert chunks[-1].metadata["scope_caveat_ranges"] == [
        {"start_line": 3, "end_line": 3}
    ]
    assert chunks[-1].metadata["scope_caveats_repeated"] is True
    assert chunks[-1].start_line == 3


def test_material_specific_caveat_does_not_leak_to_other_sections():
    text = "# Materials\n\n## PA12\n\nFatigue is not verified for PA12.\n\n" + "Polymer details. " * 30 + "\n\n## Titanium\n\nYield is 880 MPa."
    chunks = chunk_text(text, "materials.md", max_chars=100)
    titanium = [c for c in chunks if c.heading == "Titanium"]
    assert titanium and all("PA12" not in c.text for c in titanium)
    assert all("Fatigue is not verified for PA12." in c.text for c in chunks if c.heading == "PA12")


def test_teaching_scope_stays_attached_to_values():
    text = "# Values\n\nThese are approximate teaching values, not design allowables.\n\n## Steel\n\nYield is 250 MPa."
    steel = [c for c in chunk_text(text, "values.md") if c.heading == "Steel"]
    assert steel and "not design allowables" in steel[0].text

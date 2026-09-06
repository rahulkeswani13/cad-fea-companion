"""ADR-018: accepted indexes survive failed rebuilds and corpus drift is visible."""
import json
from pathlib import Path

import pytest

import companion.rag.store as rag
from companion.config import Settings
from companion.rag.corpus import manifest_entries


@pytest.fixture
def isolated_index(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, vectorstore_dir=tmp_path / 'index')
    monkeypatch.setattr(rag, 'get_settings', lambda: settings)
    monkeypatch.setattr(rag, '_STORE', None)
    corpus = tmp_path / 'reference'
    corpus.mkdir()
    (corpus / 'a.md').write_text('# Material\n\nTitanium yield is 880 MPa.\n')
    return corpus


def test_content_edit_same_chunk_count_changes_fingerprint(isolated_index):
    first = rag.ingest_docs([isolated_index])
    (isolated_index / 'a.md').write_text('# Material\n\nTitanium yield is 881 MPa.\n')
    second = rag.ingest_docs([isolated_index])
    assert first['ok'] and second['ok']
    assert first['total_chunks'] == second['total_chunks']
    assert first['fingerprint'] != second['fingerprint']
    assert '881' in rag.retrieve('titanium')[0]['text']


def test_reuse_preserves_snapshot_and_mtime(isolated_index):
    first = rag.ingest_docs([isolated_index])
    store = rag.get_store()
    before = store.path.stat().st_mtime_ns
    second = rag.ingest_docs([isolated_index], reuse_if_unchanged=True)
    assert first['ok'] and second['reused']
    assert rag.get_store() is store
    assert store.path.stat().st_mtime_ns == before
    assert not store.path.with_suffix('.previous.json').exists()


def test_read_failure_retains_accepted_index(isolated_index, monkeypatch):
    assert rag.ingest_docs([isolated_index])['ok']
    accepted = rag.get_store()
    data = accepted.path.read_bytes()
    original = Path.read_text
    def failed(path, *args, **kwargs):
        if path == isolated_index / 'a.md':
            raise OSError('unreadable')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', failed)
    result = rag.ingest_docs([isolated_index])
    assert not result['ok'] and result['correction']
    assert rag.get_store() is accepted
    assert accepted.path.read_bytes() == data
    assert rag.retrieve('titanium')


def test_build_failure_and_empty_selection_retain_accepted(isolated_index, monkeypatch):
    assert rag.ingest_docs([isolated_index])['ok']
    accepted = rag.get_store()
    assert not rag.ingest_docs([])['ok']
    def failed(self, *args, **kwargs):
        raise ValueError('empty vocabulary')
    monkeypatch.setattr(rag.LocalTfidfStore, 'build', failed)
    assert not rag.ingest_docs([isolated_index])['ok']
    assert rag.get_store() is accepted


def test_atomic_replace_failure_keeps_disk_and_memory(isolated_index, monkeypatch):
    assert rag.ingest_docs([isolated_index])['ok']
    accepted = rag.get_store()
    original = accepted.path.read_bytes()
    (isolated_index / 'a.md').write_text('# Steel\n\nSteel yield is 250 MPa.')
    replace = rag.os.replace
    def failed(source, target):
        if target == accepted.path:
            raise OSError('replace failed')
        return replace(source, target)
    monkeypatch.setattr(rag.os, 'replace', failed)
    assert not rag.ingest_docs([isolated_index])['ok']
    assert rag.get_store() is accepted
    assert accepted.path.read_bytes() == original
    assert not list(accepted.path.parent.glob('.rag-*'))


def test_rollback_and_restart_restore_previous_content(isolated_index, monkeypatch):
    first = rag.ingest_docs([isolated_index])
    (isolated_index / 'a.md').write_text('# Steel\n\nSteel yield is 250 MPa.')
    assert rag.ingest_docs([isolated_index])['ok']
    assert rag.rollback_index()['fingerprint'] == first['fingerprint']
    monkeypatch.setattr(rag, '_STORE', None)
    assert '880' in rag.retrieve('titanium')[0]['text']
    assert rag.get_store().index_metadata['fingerprint'] == first['fingerprint']


def test_manifest_only_declares_references_and_excludes_adrs():
    entries = manifest_entries()
    assert entries and all(e['path'].startswith('docs/reference/') for e in entries)
    assert not any('/adr/' in e['path'] for e in entries)
    assert {s for _, s in rag.collect_corpus_files()} == {e['path'] for e in entries}


def test_manifest_rejects_duplicate_and_traversal(tmp_path):
    entry = manifest_entries()[0]
    manifest = tmp_path / 'manifest.json'
    for entries in ([entry, entry], [{**entry, 'path': 'docs/reference/../PLAN.md'}]):
        manifest.write_text(json.dumps({'version': 1, 'documents': entries}))
        with pytest.raises(ValueError):
            manifest_entries(manifest)


def test_metadata_edit_changes_fingerprint():
    one = [{'path': 'a', 'chunks': 1, 'content_sha256': 'abc', 'metadata': {'version': '1'}}]
    two = [{**one[0], 'metadata': {'version': '2'}}]
    assert rag.corpus_fingerprint(one) != rag.corpus_fingerprint(two)

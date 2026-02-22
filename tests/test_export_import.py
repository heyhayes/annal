"""Tests for export/import CLI functions."""

import json

import pytest

from annal.config import AnnalConfig
from annal.server import _run_export, _run_import, _make_backend
from tests.conftest import make_store


@pytest.fixture
def project_with_data(tmp_data_dir, tmp_config_path):
    """Set up a project with a few memories for export testing."""
    config = AnnalConfig(
        config_path=tmp_config_path,
        data_dir=tmp_data_dir,
        projects={},
    )
    config.save()

    store = make_store(tmp_data_dir, "export_test")
    store.store("First memory about auth", tags=["auth", "decision"], source="session")
    store.store("Second memory about billing", tags=["billing"], source="design-doc")
    store.store("Third memory about testing", tags=["testing"])

    return config, tmp_data_dir


def test_make_backend_chromadb(tmp_data_dir, tmp_config_path):
    """_make_backend should create a ChromaBackend for 'chromadb'."""
    from annal.backends.chromadb import ChromaBackend

    config = AnnalConfig(config_path=tmp_config_path, data_dir=tmp_data_dir, projects={})
    backend = _make_backend("chromadb", config, "annal_test", 384)
    assert isinstance(backend, ChromaBackend)


def test_make_backend_unknown_raises(tmp_config_path, tmp_data_dir):
    """_make_backend should raise ValueError for unknown backends."""
    config = AnnalConfig(config_path=tmp_config_path, data_dir=tmp_data_dir, projects={})
    with pytest.raises(ValueError, match="Unknown backend"):
        _make_backend("sqlite", config, "annal_test", 384)


def test_export_writes_jsonl(project_with_data, capsys):
    """_run_export should write one JSON line per memory to stdout."""
    config, _ = project_with_data

    _run_export(config, "export_test")

    captured = capsys.readouterr()
    lines = [l for l in captured.out.strip().split("\n") if l]
    assert len(lines) == 3

    for line in lines:
        record = json.loads(line)
        assert "id" in record
        assert "text" in record
        assert "metadata" in record
        assert "tags" in record["metadata"]


def test_export_import_roundtrip(project_with_data, tmp_path, capsys):
    """Export then import into a new project should produce identical memories."""
    config, _ = project_with_data

    # Export
    _run_export(config, "export_test")
    captured = capsys.readouterr()
    export_lines = [l for l in captured.out.strip().split("\n") if l]

    # Write to a temp file
    jsonl_file = tmp_path / "export.jsonl"
    jsonl_file.write_text(captured.out)

    # Import into a fresh project
    _run_import(config, "roundtrip_test", str(jsonl_file))

    # Verify the imported data matches
    store = make_store(str(config.data_dir), "roundtrip_test")
    assert store.count() == 3

    # Check we can search and find the imported content
    results = store.search("auth", limit=5)
    auth_texts = [r["content"] for r in results]
    assert any("auth" in t.lower() for t in auth_texts)


def test_import_preserves_metadata(project_with_data, tmp_path, capsys):
    """Imported memories should retain their original tags, source, and chunk_type."""
    config, _ = project_with_data

    _run_export(config, "export_test")
    captured = capsys.readouterr()

    jsonl_file = tmp_path / "export.jsonl"
    jsonl_file.write_text(captured.out)

    _run_import(config, "meta_test", str(jsonl_file))

    store = make_store(str(config.data_dir), "meta_test")
    all_mems, total = store.browse(offset=0, limit=50)
    assert total == 3

    # Find the auth memory and check its metadata
    auth_mem = next(m for m in all_mems if "auth" in m["content"].lower())
    assert "auth" in auth_mem["tags"]
    assert "decision" in auth_mem["tags"]
    assert auth_mem["source"] == "session"


def test_import_skips_blank_lines(tmp_data_dir, tmp_config_path, tmp_path):
    """_run_import should skip blank lines in the JSONL file."""
    config = AnnalConfig(config_path=tmp_config_path, data_dir=tmp_data_dir, projects={})

    jsonl_file = tmp_path / "sparse.jsonl"
    records = [
        {"id": "test-1", "text": "First record", "metadata": {"tags": ["a"], "source": "", "chunk_type": "agent-memory", "created_at": "2026-01-01T00:00:00"}},
        {"id": "test-2", "text": "Second record", "metadata": {"tags": ["b"], "source": "", "chunk_type": "agent-memory", "created_at": "2026-01-01T00:00:00"}},
    ]
    content = json.dumps(records[0]) + "\n\n\n" + json.dumps(records[1]) + "\n"
    jsonl_file.write_text(content)

    _run_import(config, "sparse_test", str(jsonl_file))

    store = make_store(tmp_data_dir, "sparse_test")
    assert store.count() == 2


def test_import_empty_file(tmp_data_dir, tmp_config_path, tmp_path):
    """_run_import with an empty file should not crash and import zero records."""
    config = AnnalConfig(config_path=tmp_config_path, data_dir=tmp_data_dir, projects={})

    jsonl_file = tmp_path / "empty.jsonl"
    jsonl_file.write_text("")

    _run_import(config, "empty_test", str(jsonl_file))

    store = make_store(tmp_data_dir, "empty_test")
    assert store.count() == 0

import os
import pytest
from annal.indexer import chunk_markdown, chunk_config_file, index_file
from tests.conftest import make_store


def test_chunk_markdown_splits_by_headings():
    content = """# Overview
This is the overview section.

## Architecture
The system has three layers.

### Backend
PHP and Laravel.

## Frontend
React and TypeScript.
"""
    chunks = chunk_markdown(content, "README.md")
    assert len(chunks) == 4
    assert chunks[0]["heading"] == "README.md > Overview"
    assert "overview section" in chunks[0]["content"]
    assert chunks[1]["heading"] == "README.md > Architecture"
    assert chunks[2]["heading"] == "README.md > Architecture > Backend"
    assert chunks[3]["heading"] == "README.md > Frontend"


def test_chunk_markdown_single_section():
    content = "Just some text without headings."
    chunks = chunk_markdown(content, "NOTES.md")
    assert len(chunks) == 1
    assert chunks[0]["heading"] == "NOTES.md"
    assert "without headings" in chunks[0]["content"]


def test_chunk_config_file():
    content = '{"key": "value", "nested": {"a": 1}}'
    chunks = chunk_config_file(content, "config.json")
    assert len(chunks) == 1
    assert chunks[0]["heading"] == "config.json"
    assert '"key"' in chunks[0]["content"]


def test_index_file_stores_chunks(tmp_data_dir, tmp_path):
    md_file = tmp_path / "test.md"
    md_file.write_text("# Section A\nContent A\n\n# Section B\nContent B\n")

    store = make_store(tmp_data_dir,"testproject")
    count = index_file(store, str(md_file))
    assert count == 2
    assert store.count() == 2

    results = store.search("Content A", limit=1)
    assert len(results) == 1
    assert results[0]["chunk_type"] == "file-indexed"


def test_chunk_markdown_recognizes_h4_through_h6():
    """Headings #### through ###### should create chunk boundaries."""
    content = """# Top Level
Intro text

## Section
Section text

### Subsection
Sub text

#### Detail
Detail text

##### Fine Detail
Fine detail text

###### Finest Detail
Finest detail text
"""
    chunks = chunk_markdown(content, "test.md")
    headings = [c["heading"] for c in chunks]
    # All heading levels should create separate chunks
    assert any("Detail" in h for h in headings)
    assert any("Fine Detail" in h for h in headings)
    assert any("Finest Detail" in h for h in headings)


def test_index_file_prepends_heading_path_to_content(tmp_data_dir, tmp_path):
    """Stored content should start with the heading path for embedding context."""
    md_file = tmp_path / "doc.md"
    md_file.write_text("# Project\nIntro\n\n## Design\n### Backend\nUses Python.\n")

    store = make_store(tmp_data_dir,"headingtest")
    index_file(store, str(md_file))

    results = store.search("Python", limit=5)
    backend_chunk = [r for r in results if "Backend" in r["source"]]
    assert len(backend_chunk) > 0
    # Content should start with heading path
    assert backend_chunk[0]["content"].startswith("doc.md")
    assert "Backend" in backend_chunk[0]["content"]
    assert "Uses Python" in backend_chunk[0]["content"]


def test_reindex_file_replaces_old_chunks(tmp_data_dir, tmp_path):
    md_file = tmp_path / "test.md"
    md_file.write_text("# Version 1\nOld content\n")

    store = make_store(tmp_data_dir,"testproject")
    index_file(store, str(md_file))
    assert store.count() == 1

    md_file.write_text("# Version 2\nNew content\n\n# Extra\nMore stuff\n")
    index_file(store, str(md_file))
    assert store.count() == 2

    results = store.search("Old content", limit=5)
    # Old content should not match well anymore since it was deleted
    for r in results:
        assert "Old content" not in r["content"]


def test_heading_context_uses_full_path(tmp_data_dir, tmp_path):
    """Stored content should start with 'filename > Heading > Subheading' format."""
    md_file = tmp_path / "doc.md"
    md_file.write_text("# Project\nIntro\n\n## Design\n### Backend\nUses Python.\n")

    store = make_store(tmp_data_dir,"heading_strict")
    index_file(store, str(md_file))

    results = store.search("Python", limit=5)
    backend_chunk = [r for r in results if "Backend" in r["source"]]
    assert len(backend_chunk) > 0
    # Content should start with the full heading path
    assert backend_chunk[0]["content"].startswith("doc.md > Design > Backend")


def test_chunk_markdown_skips_empty_parent_headings():
    """Headings with no body (only sub-headings) should not produce chunks."""
    content = """## Parent
### Child
Child body text here.
"""
    chunks = chunk_markdown(content, "test.md")
    # Only the child should produce a chunk, not the empty parent
    assert len(chunks) == 1
    assert "Child body text here" in chunks[0]["content"]
    # No chunk should have just "Parent" as its content
    for chunk in chunks:
        assert chunk["content"] != "Parent"

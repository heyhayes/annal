"""File indexing and markdown chunking for Annal."""

from __future__ import annotations

import re
from pathlib import Path

from annal.store import MemoryStore


def chunk_markdown(content: str, filename: str) -> list[dict]:
    """Split markdown content into chunks by heading boundaries."""
    lines = content.split("\n")
    chunks = []
    current_content: list[str] = []
    heading_stack: list[str] = []
    heading_levels: list[int] = []
    current_heading = filename

    last_heading_text = ""

    for line in lines:
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            # Save previous chunk
            text = "\n".join(current_content).strip()
            if text:
                chunks.append({"heading": current_heading, "content": text})
            elif last_heading_text:
                # Heading-only section — use heading text as content
                chunks.append({"heading": current_heading, "content": last_heading_text})
            current_content = []

            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            last_heading_text = heading_text

            # Update heading stack — pop headings at same or deeper level
            while heading_levels and heading_levels[-1] >= level:
                heading_levels.pop()
                heading_stack.pop()

            # h1 headings are top-level section markers, not nesting parents
            if level > 1:
                heading_stack.append(heading_text)
                heading_levels.append(level)
                current_heading = filename + " > " + " > ".join(heading_stack)
            else:
                heading_stack.clear()
                heading_levels.clear()
                current_heading = filename + " > " + heading_text
        else:
            current_content.append(line)

    # Don't forget the last chunk
    text = "\n".join(current_content).strip()
    if text:
        chunks.append({"heading": current_heading, "content": text})
    elif last_heading_text:
        chunks.append({"heading": current_heading, "content": last_heading_text})

    return chunks


def chunk_config_file(content: str, filename: str) -> list[dict]:
    """Treat an entire config file as a single chunk."""
    return [{"heading": filename, "content": content.strip()}]


def index_file(store: MemoryStore, file_path: str, file_mtime: float | None = None) -> int:
    """Index a file into the memory store. Returns number of chunks created."""
    path = Path(file_path)
    if not path.exists():
        return 0

    content = path.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        return 0

    if file_mtime is None:
        file_mtime = path.stat().st_mtime

    # Delete any existing chunks from this file
    store.delete_by_source(f"file:{file_path}")

    # Chunk based on file type
    suffix = path.suffix.lower()
    if suffix == ".md":
        chunks = chunk_markdown(content, path.name)
    elif suffix in (".json", ".yaml", ".yml", ".toml"):
        chunks = chunk_config_file(content, path.name)
    else:
        chunks = [{"heading": path.name, "content": content}]

    # Store each chunk
    for chunk in chunks:
        tags = _derive_tags(path)
        store.store(
            content=chunk["content"],
            tags=tags,
            source=f"file:{file_path}|{chunk['heading']}",
            chunk_type="file-indexed",
            file_mtime=file_mtime,
        )

    return len(chunks)


def _derive_tags(path: Path) -> list[str]:
    """Derive automatic tags from the file path."""
    tags = ["indexed"]
    name_lower = path.name.lower()
    if "claude" in name_lower or "agent" in name_lower:
        tags.append("agent-config")
    if "readme" in name_lower:
        tags.append("docs")
    return tags

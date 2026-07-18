"""Tests for the paper builder — TODO tagging and end-to-end HTML render.

The end-to-end HTML render invokes pandoc as a subprocess. It skips
gracefully if pandoc is not installed (CI installs pandoc explicitly;
local dev environments may not have it). The TODO-tagging unit tests
run everywhere because they only touch the pure-string post-processor.

PDF rendering is not exercised in the test suite — it requires the
``paper`` extra plus system Pango libraries, which would balloon the
default test install. Live PDF renders are covered by the ``make paper``
smoke run during release preparation.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from paper.build import build_html, postprocess_todo_markers

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# postprocess_todo_markers — pure string transform, always runs
# ---------------------------------------------------------------------------


def test_block_todo_paragraph_tagged() -> None:
    """A whole-paragraph TODO becomes a callout-classed <p>."""
    html = "<p><code>[TODO: fill in]</code></p>"
    out = postprocess_todo_markers(html)
    assert '<p class="todo">' in out
    # Inner <code> is replaced with a <span> so the inline pass does not
    # re-mark a block-level TODO.
    assert "<span>[TODO: fill in]</span></p>" in out
    assert 'code class="todo-inline"' not in out


def test_inline_todo_span_tagged() -> None:
    """An inline TODO inside prose becomes .todo-inline."""
    html = "<p>Some prose then <code>[TODO: fix]</code> more prose.</p>"
    out = postprocess_todo_markers(html)
    assert 'code class="todo-inline"' in out
    # The outer <p> is not touched — this is not a block-level TODO.
    assert '<p class="todo">' not in out


def test_block_and_inline_todos_do_not_conflict() -> None:
    """Block match runs first; inline match sees the remaining spans."""
    html = (
        "<p><code>[TODO: full section]</code></p>"
        "<p>Some prose <code>[TODO: one word]</code> more.</p>"
    )
    out = postprocess_todo_markers(html)
    assert out.count('p class="todo"') == 1
    assert out.count('code class="todo-inline"') == 1


def test_non_todo_code_spans_untouched() -> None:
    """Regular ``<code>`` samples in the paper must not get tagged."""
    html = "<p>Run <code>make replicate</code> to reproduce.</p>"
    out = postprocess_todo_markers(html)
    assert 'class="todo' not in out


def test_todo_with_hyphen_or_colon_matched() -> None:
    """Both ``[TODO —`` and ``[TODO:`` forms are picked up."""
    html = (
        "<p><code>[TODO — long form]</code></p>"
        "<p>See <code>[TODO: short form]</code> here.</p>"
    )
    out = postprocess_todo_markers(html)
    assert '<p class="todo">' in out
    assert 'code class="todo-inline"' in out


# ---------------------------------------------------------------------------
# build_html — subprocess to pandoc; skipped if pandoc missing
# ---------------------------------------------------------------------------


PANDOC_AVAILABLE = shutil.which("pandoc") is not None


@pytest.mark.skipif(
    not PANDOC_AVAILABLE,
    reason="pandoc not installed on PATH — skipping subprocess render",
)
def test_build_html_produces_valid_html(tmp_path: Path) -> None:
    """A minimal markdown source renders to standalone HTML with TOC."""
    source = tmp_path / "mini.md"
    source.write_text(
        "# Title\n\n## Section 1\n\nSome prose.\n\n"
        "## Section 2\n\n`[TODO: fill this in]`\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.html"
    build_html(source, out)
    assert out.is_file()
    html = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html or "<html" in html.lower()
    # TOC generated from H2 headings.
    assert 'id="TOC"' in html
    # TODO paragraph tagged.
    assert '<p class="todo">' in html


@pytest.mark.skipif(
    not PANDOC_AVAILABLE,
    reason="pandoc not installed on PATH — skipping subprocess render",
)
def test_build_html_renders_bundled_paper(tmp_path: Path) -> None:
    """The bundled paper/paper.md renders without error."""
    from pathlib import Path as PathType

    repo_root = PathType(__file__).resolve().parent.parent
    source = repo_root / "paper" / "paper.md"
    out = tmp_path / "paper.html"
    build_html(source, out)
    assert out.is_file()
    html = out.read_text(encoding="utf-8")
    # Sanity: the paper has real TODO markers we know about.
    assert '<p class="todo">' in html
    assert "Pre-Send Leakage Benchmark" in html

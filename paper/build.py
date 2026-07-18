"""Build the paper's HTML and PDF from ``paper/paper.md``.

Pandoc + Weasyprint. Pipeline:

1. Pre-process ``paper.md`` to wrap any paragraph starting with
   ``[TODO`` in a ``<div class="todo">`` — Pandoc's markdown doesn't
   let us style bracketed prose per-paragraph without help.
2. Run Pandoc: markdown → self-contained HTML with our CSS embedded
   and a table of contents generated from H2 / H3 headings.
3. Run Weasyprint: HTML → PDF.

Two artifacts are written to ``paper/`` (both gitignored):

- ``paper/paper.html`` — for the paper site + shareable link
- ``paper/paper.pdf``  — for email + citation + Google-Docs paste

Usage
-----
::

    uv run python -m paper.build

Requires: Pandoc installed on ``PATH`` and the ``paper`` extra
(``uv sync --extra paper``).
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

LOGGER = logging.getLogger(__name__)

PAPER_DIR: Final[Path] = Path(__file__).parent
SOURCE_MD: Final[Path] = PAPER_DIR / "paper.md"
STYLE_CSS: Final[Path] = PAPER_DIR / "style.css"
OUT_HTML: Final[Path] = PAPER_DIR / "paper.html"
OUT_PDF: Final[Path] = PAPER_DIR / "paper.pdf"

# TODO markers in paper.md are backtick-wrapped code spans starting with
# `[TODO`. Pandoc turns those into ``<code>[TODO ...]</code>``. We patch
# the emitted HTML to add the ``.todo`` class so style.css renders them
# as highlighted callouts. Two shapes covered:
#
#   1. Block-level  — <p><code>[TODO ...]</code></p>  →  wrap <p> as .todo
#   2. Inline       — <code>[TODO ...]</code> inside prose  →  .todo-inline
#
# Order matters: the block-level pattern must run first (its match is a
# superset of the inline pattern's).
_BLOCK_TODO_RE: Final[re.Pattern[str]] = re.compile(
    r"<p><code>(\[TODO[^<]*)</code></p>",
)
_INLINE_TODO_RE: Final[re.Pattern[str]] = re.compile(
    r"<code>(\[TODO[^<]*)</code>",
)


def postprocess_todo_markers(html: str) -> str:
    """Tag TODO code spans so CSS can render them as callouts.

    Block-level runs first and replaces the inner ``<code>`` with a
    plain ``<span>`` so the inline pattern's follow-up pass does not
    match a block-level TODO twice.
    """
    html = _BLOCK_TODO_RE.sub(
        r'<p class="todo"><span>\1</span></p>',
        html,
    )
    return _INLINE_TODO_RE.sub(
        r'<code class="todo-inline">\1</code>',
        html,
    )


def _ensure_pandoc() -> str:
    """Verify pandoc is on PATH; fail loud with an install hint if not."""
    binary = shutil.which("pandoc")
    if binary is None:
        msg = (
            "pandoc not found on PATH. Install: "
            "`brew install pandoc` (macOS) or "
            "`apt install pandoc` (Debian/Ubuntu)."
        )
        raise RuntimeError(msg)
    return binary


def _ensure_weasyprint() -> None:
    """Import weasyprint lazily so ``--html-only`` works without it."""
    try:
        import weasyprint  # noqa: F401
    except ImportError as exc:
        msg = (
            "weasyprint is not installed. Install with "
            "`uv sync --extra paper` (macOS also needs `brew install pango`)."
        )
        raise RuntimeError(msg) from exc


def build_html(source_md: Path, out_html: Path) -> None:
    """Render markdown to a self-contained HTML file with embedded CSS."""
    pandoc = _ensure_pandoc()
    out_html.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(  # noqa: S603 - pandoc binary path validated above
        [
            pandoc,
            "--from",
            "markdown+fenced_divs+backtick_code_blocks",
            "--to",
            "html5",
            "--standalone",
            "--toc",
            "--toc-depth=3",
            "--section-divs",
            "--css",
            str(STYLE_CSS.name),
            "--metadata",
            "title=LLM Pre-Send Leakage Benchmark v1.0",
            "--metadata",
            "lang=en",
        ],
        input=source_md.read_text(encoding="utf-8"),
        text=True,
        check=True,
        capture_output=True,
        cwd=str(PAPER_DIR),
    )
    out_html.write_text(postprocess_todo_markers(result.stdout), encoding="utf-8")
    LOGGER.info("Wrote %s (%d bytes)", out_html, out_html.stat().st_size)


def build_pdf(html_path: Path, out_pdf: Path) -> None:
    """Render the HTML to a print-ready PDF via weasyprint."""
    _ensure_weasyprint()
    from weasyprint import HTML

    HTML(filename=str(html_path)).write_pdf(target=str(out_pdf))
    LOGGER.info("Wrote %s (%d bytes)", out_pdf, out_pdf.stat().st_size)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns process exit code."""
    parser = argparse.ArgumentParser(
        description="Build HTML and PDF from paper/paper.md.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=SOURCE_MD,
        help=f"Source markdown file (default: {SOURCE_MD}).",
    )
    parser.add_argument(
        "--out-html",
        type=Path,
        default=OUT_HTML,
        help=f"HTML output path (default: {OUT_HTML}).",
    )
    parser.add_argument(
        "--out-pdf",
        type=Path,
        default=OUT_PDF,
        help=f"PDF output path (default: {OUT_PDF}).",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Skip PDF render — useful when weasyprint is unavailable.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.source.is_file():
        LOGGER.error("Source not found: %s", args.source)
        return 1

    build_html(args.source, args.out_html)
    if not args.html_only:
        build_pdf(args.out_html, args.out_pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())

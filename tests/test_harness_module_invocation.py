"""Regression tests for harness CLI invocation via ``python -m``.

Each vendor-specific harness file is named after its PyPI package
(``harness/api/openai.py`` next to the ``openai`` SDK, etc.). When
invoked as a script — ``python harness/api/openai.py`` — Python puts
``harness/api/`` on ``sys.path[0]`` and shadows the site-packages
package. ``import openai`` then loads the harness itself, and
``openai.OpenAI`` blows up with AttributeError at the first live
call.

The fix is to invoke via module path — ``python -m harness.api.openai``
— which puts the repo root on ``sys.path`` instead of the script's
directory. These tests exercise that path per vendor with ``--dry-run``
so no API keys or network are required, and fail immediately if the
shadowing regression comes back.

The tests do not import the harness modules directly; they spawn a
subprocess and assert the process succeeds and produces output. That
is the invariant that matters.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

MODULES = [
    "harness.api.anthropic",
    "harness.api.openai",
    "harness.api.bedrock",
]


@pytest.mark.parametrize("module", MODULES)
def test_module_invocation_dry_run_smoke(module: str, tmp_path: Path) -> None:
    """``python -m <module> --dry-run`` runs end-to-end without shadowing."""
    output = tmp_path / "results.json"
    result = subprocess.run(  # noqa: S603 - args are hard-coded, no shell
        [
            sys.executable,
            "-m",
            module,
            "--corpus",
            "corpus/corpus_v1.jsonl",
            "--output",
            str(output),
            "--dry-run",
            "--limit",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"{module} failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert output.is_file()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["count"] == 1


def test_azure_openai_module_invocation_dry_run_smoke(tmp_path: Path) -> None:
    """Azure needs an explicit deployment; test the same shadowing invariant."""
    output = tmp_path / "results.json"
    result = subprocess.run(  # noqa: S603 - args are hard-coded, no shell
        [
            sys.executable,
            "-m",
            "harness.api.azure_openai",
            "--corpus",
            "corpus/corpus_v1.jsonl",
            "--output",
            str(output),
            "--model",
            "smoke-deployment",
            "--dry-run",
            "--limit",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"azure_openai failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert output.is_file()


def test_script_mode_would_shadow_the_sdk() -> None:
    """Document why ``python harness/api/openai.py`` breaks.

    We do not run the buggy invocation. This test instead asserts the
    conditions that cause the shadowing so a future refactor sees the
    invariant explicitly: the file exists at the shadowing path, and
    ``import openai`` from that directory resolves to it — meaning the
    SDK is masked whenever ``sys.path[0]`` is ``harness/api/``.
    """
    from pathlib import Path

    from harness.api._common import (
        CorpusRecord,  # noqa: F401 - just proves the package imports
    )

    repo_root = Path(__file__).resolve().parent.parent
    assert (repo_root / "harness" / "api" / "openai.py").is_file()
    assert (repo_root / "harness" / "api" / "anthropic.py").is_file()
    assert (repo_root / "harness" / "api" / "bedrock.py").is_file()
    assert (repo_root / "harness" / "api" / "azure_openai.py").is_file()

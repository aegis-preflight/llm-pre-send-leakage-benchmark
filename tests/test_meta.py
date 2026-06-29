"""Meta tests — verify the dev environment is set up correctly.

These run on every CI matrix entry to confirm the scaffold itself is healthy
before any benchmark-specific tests run.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_python_version_meets_minimum() -> None:
    """Project requires Python 3.11+."""
    assert sys.version_info >= (3, 11), (
        f"Python 3.11+ required; got {sys.version_info[:2]}"
    )


def test_repo_foundational_files_exist() -> None:
    """Repository contains the foundational files reviewers expect."""
    expected = [
        "README.md",
        "LICENSE",
        "CITATION.cff",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "pyproject.toml",
        ".gitignore",
        ".gitattributes",
        ".pre-commit-config.yaml",
        ".gitleaks.toml",
        "Makefile",
    ]
    missing = [f for f in expected if not (REPO_ROOT / f).is_file()]
    assert not missing, f"Missing foundational files: {missing}"


def test_package_dirs_have_init_files() -> None:
    """Source package directories are importable (have __init__.py)."""
    expected_packages = ["corpus", "harness", "harness/api", "harness/web", "tests"]
    missing = [
        p for p in expected_packages if not (REPO_ROOT / p / "__init__.py").is_file()
    ]
    assert not missing, f"Missing __init__.py in: {missing}"


def test_required_dev_packages_importable() -> None:
    """Core dev dependencies are installed and importable."""
    import faker  # noqa: F401
    import pytest  # noqa: F401


def test_ci_workflow_exists() -> None:
    """GitHub Actions CI workflow is in place."""
    ci_file = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_file.is_file(), "CI workflow missing"


def test_license_is_mit() -> None:
    """LICENSE file declares MIT."""
    license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text, "LICENSE is not MIT"

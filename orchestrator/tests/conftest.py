"""テスト共通のフィクスチャ。"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.prompts import PROMPTS_PATH_ENV


@pytest.fixture(autouse=True)
def _isolated_prompts_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """実環境のconfig/prompts.yamlの上書きがテストに影響しないよう、一時パスに差し替える。"""
    path = tmp_path / "prompts.yaml"
    monkeypatch.setenv(PROMPTS_PATH_ENV, str(path))
    return path

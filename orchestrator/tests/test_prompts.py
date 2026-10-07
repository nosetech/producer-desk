"""orchestrator/prompts.py のテスト（issue #149）。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from orchestrator.prompts import (
    USER_NAME_SPEC,
    PromptSpec,
    PromptValidationError,
    RequiredToken,
    describe_prompt,
    load_overrides,
    load_prompt_text,
    render_prompt,
    reset_prompt_override,
    save_prompt_override,
    validate_prompt_text,
)

SPEC = PromptSpec(
    key="sample",
    title="サンプル",
    description="テスト用",
    default="{repo}#{issue_number} を処理 <!-- marker -->",
    required_tokens=(RequiredToken("<!-- marker -->", "テスト用マーカー"),),
)


def test_validate_accepts_default() -> None:
    assert validate_prompt_text(SPEC, SPEC.default) == []


def test_validate_rejects_empty_text() -> None:
    errors = validate_prompt_text(PromptSpec("k", "t", "d", "x"), "  ")

    assert errors == ["本文が空です"]


def test_validate_rejects_missing_required_token() -> None:
    errors = validate_prompt_text(SPEC, "{repo} だけ")

    assert errors == ["必須トークン <!-- marker --> が含まれていません"]


def test_validate_rejects_unknown_placeholder() -> None:
    errors = validate_prompt_text(SPEC, "{foo} <!-- marker -->")

    assert len(errors) == 1
    assert "{foo}" in errors[0]


def test_validate_allows_json_example_braces() -> None:
    text = '{"pr_number": 1} <!-- marker -->'

    assert validate_prompt_text(SPEC, text) == []


def test_render_replaces_placeholders_without_touching_json_braces() -> None:
    rendered = render_prompt(
        '{repo} {issue_number} {user_name} {"a": 1}', repo="o/r", issue_number=7, user_name="先生"
    )

    assert rendered == 'o/r 7 先生 {"a": 1}'


def test_load_returns_default_when_file_missing(tmp_path: Path) -> None:
    assert load_prompt_text(SPEC, tmp_path / "none.yaml") == SPEC.default


def test_save_persists_override_and_load_reads_it(tmp_path: Path) -> None:
    path = tmp_path / "prompts.yaml"

    save_prompt_override(SPEC, "新しい本文 <!-- marker -->", path)

    assert load_prompt_text(SPEC, path) == "新しい本文 <!-- marker -->"
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == {
        "prompts": {"sample": "新しい本文 <!-- marker -->"}
    }


def test_save_keeps_other_overrides(tmp_path: Path) -> None:
    path = tmp_path / "prompts.yaml"
    path.write_text(yaml.safe_dump({"prompts": {"other": "keep"}}), encoding="utf-8")

    save_prompt_override(SPEC, "変更 <!-- marker -->", path)

    assert load_overrides(path) == {"other": "keep", "sample": "変更 <!-- marker -->"}


def test_save_rejects_invalid_text_and_does_not_write(tmp_path: Path) -> None:
    path = tmp_path / "prompts.yaml"

    with pytest.raises(PromptValidationError) as exc_info:
        save_prompt_override(SPEC, "マーカー無し", path)

    assert exc_info.value.errors == ["必須トークン <!-- marker --> が含まれていません"]
    assert not path.exists()


def test_save_default_text_removes_override(tmp_path: Path) -> None:
    path = tmp_path / "prompts.yaml"
    save_prompt_override(SPEC, "変更 <!-- marker -->", path)

    save_prompt_override(SPEC, SPEC.default, path)

    assert load_overrides(path) == {}


def test_reset_removes_override(tmp_path: Path) -> None:
    path = tmp_path / "prompts.yaml"
    save_prompt_override(SPEC, "変更 <!-- marker -->", path)

    reset_prompt_override(SPEC, path)

    assert load_prompt_text(SPEC, path) == SPEC.default


def test_reset_without_override_is_noop(tmp_path: Path) -> None:
    path = tmp_path / "prompts.yaml"

    reset_prompt_override(SPEC, path)

    assert not path.exists()


def test_load_falls_back_to_default_when_hand_edited_override_is_invalid(
    tmp_path: Path,
) -> None:
    path = tmp_path / "prompts.yaml"
    path.write_text(yaml.safe_dump({"prompts": {"sample": "マーカー無し"}}), encoding="utf-8")

    assert load_prompt_text(SPEC, path) == SPEC.default


def test_load_falls_back_to_default_when_yaml_is_broken(tmp_path: Path) -> None:
    path = tmp_path / "prompts.yaml"
    path.write_text("prompts: [unclosed", encoding="utf-8")

    assert load_prompt_text(SPEC, path) == SPEC.default


def test_describe_prompt_reports_state(tmp_path: Path) -> None:
    path = tmp_path / "prompts.yaml"

    assert describe_prompt(SPEC, path)["is_default"] is True
    save_prompt_override(SPEC, "変更 <!-- marker -->", path)
    info = describe_prompt(SPEC, path)

    assert info["is_default"] is False
    assert info["text"] == "変更 <!-- marker -->"
    assert info["default"] == SPEC.default
    assert info["required_tokens"] == [{"token": "<!-- marker -->", "reason": "テスト用マーカー"}]
    assert info["placeholders"] == ["repo", "issue_number", "user_name"]
    assert info["multiline"] is True


def test_validate_allows_user_name_placeholder() -> None:
    assert validate_prompt_text(SPEC, "{user_name} <!-- marker -->") == []


def test_user_name_spec_defaults_to_user() -> None:
    assert USER_NAME_SPEC.default == "ユーザー"


@pytest.mark.parametrize("text", ["山田\n太郎", "{repo}", "山田{", "}"])
def test_user_name_rejects_newline_and_braces(text: str) -> None:
    assert validate_prompt_text(USER_NAME_SPEC, text) != []


def test_user_name_accepts_plain_name(tmp_path: Path) -> None:
    path = tmp_path / "prompts.yaml"

    save_prompt_override(USER_NAME_SPEC, "山田さん", path)

    assert load_prompt_text(USER_NAME_SPEC, path) == "山田さん"
    assert describe_prompt(USER_NAME_SPEC, path)["multiline"] is False


def test_describe_prompt_expands_user_name_in_description_and_reasons(tmp_path: Path) -> None:
    path = tmp_path / "prompts.yaml"
    spec = PromptSpec(
        key="sample",
        title="t",
        description="{user_name}向けの説明",
        default="x <!-- marker -->",
        required_tokens=(RequiredToken("<!-- marker -->", "{user_name}の判断に必要"),),
    )

    default_info = describe_prompt(spec, path)
    save_prompt_override(USER_NAME_SPEC, "山田さん", path)
    named_info = describe_prompt(spec, path)

    assert default_info["description"] == "ユーザー向けの説明"
    assert named_info["description"] == "山田さん向けの説明"
    assert named_info["required_tokens"][0]["reason"] == "山田さんの判断に必要"

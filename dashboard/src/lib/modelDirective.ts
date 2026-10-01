// issueコメント本文の`/model <値>`ディレクティブ（orchestrator/orchestrator/execution_mode.py
// の`parse_override_directive`）をUIから自動挿入するためのヘルパー。

/** セレクタ上の「プロジェクトの既定のまま」を表す値（ディレクティブを挿入しない）。 */
export const MODEL_DEFAULT = "default";

export interface ModelOption {
  id: string;
  label: string;
}

export function modelOptions(availableModels: string[]): ModelOption[] {
  return [
    { id: MODEL_DEFAULT, label: "プロジェクトの既定のまま" },
    { id: "claude_code", label: "Claude Code" },
    ...availableModels.map((alias) => ({
      id: `litellm:${alias}`,
      label: `LiteLLM · ${alias}`,
    })),
  ];
}

/**
 * 本文先頭の`/model …`行（と直後の空行）を取り除き、`model`が既定以外なら
 * 先頭に独立した行＋空行として挿入し直す。UI上は常に高々1行のみ保つ。
 */
export function applyModelDirective(text: string, model: string): string {
  const stripped = text.replace(/^\/model [^\n]*\n(\n)?/, "");
  return model === MODEL_DEFAULT ? stripped : `/model ${model}\n\n${stripped}`;
}

import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";
import { parse } from "yaml";
import type { ExecutionMode, ProjectExecutionSettings } from "./types";

interface ProjectEntry {
  repo: string;
  worktree_path?: string;
  session_id?: string | null;
  execution_mode?: ExecutionMode;
  litellm_model?: string | null;
}

const CONFIG_PATH = path.join(process.cwd(), "..", "config", "projects.yaml");
const LITELLM_CONFIG_PATH = path.join(
  process.cwd(),
  "..",
  "config",
  "litellm_config.yaml",
);

async function loadProjectEntries(): Promise<ProjectEntry[]> {
  let raw: string;
  try {
    raw = await readFile(CONFIG_PATH, "utf-8");
  } catch {
    return [];
  }
  const data = parse(raw) as { projects?: ProjectEntry[] } | null;
  return data?.projects ?? [];
}

/** `config/projects.yaml`（docs/basic-design.md 2-1）に登録された対象リポジトリ一覧を読む。 */
export async function loadProjectRepos(): Promise<string[]> {
  return (await loadProjectEntries()).map((p) => p.repo);
}

function toExecutionSettings(
  entry: ProjectEntry | undefined,
): ProjectExecutionSettings {
  const executionMode = entry?.execution_mode ?? "claude_code";
  return {
    execution_mode: executionMode,
    litellm_model:
      executionMode === "litellm_proxy" ? (entry?.litellm_model ?? null) : null,
  };
}

/**
 * `GET /api/projects`向け: 対象リポジトリ一覧と実行手段設定を`config/projects.yaml`の
 * 1回の読み込み・パースでまとめて返す（それぞれ個別に読むと同一リクエスト内でファイルI/O・
 * YAMLパースが重複するため）。
 */
export async function loadProjectsWithExecutionSettings(): Promise<{
  repos: string[];
  settings: Record<string, ProjectExecutionSettings>;
}> {
  const entries = await loadProjectEntries();
  const settings: Record<string, ProjectExecutionSettings> = {};
  for (const entry of entries) {
    settings[entry.repo] = toExecutionSettings(entry);
  }
  return { repos: entries.map((p) => p.repo), settings };
}

/** 単一プロジェクトの実行手段設定を読む。未登録リポジトリは既定値（claude_code）を返す。 */
export async function loadProjectExecutionSettings(
  repo: string,
): Promise<ProjectExecutionSettings> {
  const entries = await loadProjectEntries();
  return toExecutionSettings(entries.find((p) => p.repo === repo));
}

interface LiteLlmModelEntry {
  model_name: string;
  model_info?: { repo?: string };
}

/**
 * `config/litellm_config.yaml`（basic-design.md 4章、issue #176）の`model_list`から、
 * 指定リポジトリ向けに定義済みのモデルエイリアス名一覧を読む。
 * `model_info.repo`でプロジェクトごとにエントリを分ける設計（repo単位の利用量帰属方法）に対応する。
 */
export async function loadLiteLlmModelsForRepo(
  repo: string,
): Promise<string[]> {
  let raw: string;
  try {
    raw = await readFile(LITELLM_CONFIG_PATH, "utf-8");
  } catch {
    return [];
  }
  const data = parse(raw) as { model_list?: LiteLlmModelEntry[] } | null;
  return (data?.model_list ?? [])
    .filter((m) => m.model_info?.repo === repo)
    .map((m) => m.model_name);
}

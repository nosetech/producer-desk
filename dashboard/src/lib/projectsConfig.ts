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

export const PROJECTS_CONFIG_PATH_ENV = "PROJECTS_CONFIG_PATH";
export const LITELLM_CONFIG_PATH_ENV = "LITELLM_CONFIG_PATH";

/**
 * 設定ファイルのパスを解決する。orchestratorと同じ環境変数（`PROJECTS_CONFIG_PATH` /
 * `LITELLM_CONFIG_PATH`）があればそれを優先する（相対パスはorchestratorと同様にプロセスの
 * cwd基準。どちらもリポジトリ直下の1階層下で起動するため同じファイルを指す）。
 * リクエストごとに環境変数を読むため、ビルド時に値が焼き込まれない。
 */
export function resolveConfigPath(
  envName: string,
  fileName: string,
): {
  path: string;
  explicit: boolean;
} {
  const fromEnv = process.env[envName];
  if (fromEnv) {
    return { path: path.resolve(fromEnv), explicit: true };
  }
  return {
    path: path.join(process.cwd(), "..", "config", fileName),
    explicit: false,
  };
}

/**
 * 設定ファイルを読む。存在しない（ENOENT）場合は`null`を返す（環境変数で明示した
 * パスの場合は設定ミスに気づけるよう警告を出す）。それ以外の失敗はログに出して`null`。
 */
async function readConfigFile(
  envName: string,
  fileName: string,
): Promise<string | null> {
  const { path: configPath, explicit } = resolveConfigPath(envName, fileName);
  try {
    return await readFile(configPath, "utf-8");
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") {
      if (explicit) {
        console.warn(
          `[projectsConfig] ${envName}で指定された設定ファイルが存在しません: ${configPath}`,
        );
      }
    } else {
      console.error(
        `[projectsConfig] 設定ファイルを読み込めません: ${configPath}`,
        e,
      );
    }
    return null;
  }
}

function parseConfigYaml<T>(raw: string, label: string): T | null {
  try {
    return parse(raw) as T | null;
  } catch (e) {
    console.error(`[projectsConfig] ${label}のYAMLを解釈できません`, e);
    return null;
  }
}

async function loadProjectEntries(): Promise<ProjectEntry[]> {
  const raw = await readConfigFile(PROJECTS_CONFIG_PATH_ENV, "projects.yaml");
  if (raw === null) return [];
  const data = parseConfigYaml<{ projects?: ProjectEntry[] }>(
    raw,
    "projects.yaml",
  );
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
  const raw = await readConfigFile(
    LITELLM_CONFIG_PATH_ENV,
    "litellm_config.yaml",
  );
  if (raw === null) return [];
  const data = parseConfigYaml<{ model_list?: LiteLlmModelEntry[] }>(
    raw,
    "litellm_config.yaml",
  );
  return (data?.model_list ?? [])
    .filter((m) => m.model_info?.repo === repo)
    .map((m) => m.model_name);
}

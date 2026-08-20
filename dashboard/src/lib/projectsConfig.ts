import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";
import { parse } from "yaml";

interface ProjectEntry {
  repo: string;
  worktree_path?: string;
  session_id?: string | null;
}

const CONFIG_PATH = path.join(process.cwd(), "..", "config", "projects.yaml");

/** `config/projects.yaml`（docs/basic-design.md 2-1）に登録された対象リポジトリ一覧を読む。 */
export async function loadProjectRepos(): Promise<string[]> {
  let raw: string;
  try {
    raw = await readFile(CONFIG_PATH, "utf-8");
  } catch {
    return [];
  }
  const data = parse(raw) as { projects?: ProjectEntry[] } | null;
  return (data?.projects ?? []).map((p) => p.repo);
}

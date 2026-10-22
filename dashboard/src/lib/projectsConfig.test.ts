import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import {
  loadProjectRepos,
  PROJECTS_CONFIG_PATH_ENV,
  resolveConfigPath,
} from "./projectsConfig";

let dir: string;

beforeEach(async () => {
  dir = await mkdtemp(path.join(tmpdir(), "projects-config-"));
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(async () => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  await rm(dir, { recursive: true, force: true });
});

describe("resolveConfigPath", () => {
  it("環境変数未設定なら従来のconfig/配下を返す", () => {
    vi.stubEnv(PROJECTS_CONFIG_PATH_ENV, "");
    const r = resolveConfigPath(PROJECTS_CONFIG_PATH_ENV, "projects.yaml");
    expect(r).toEqual({
      path: path.join(process.cwd(), "..", "config", "projects.yaml"),
      explicit: false,
    });
  });

  it("環境変数があればそのパスを優先する", () => {
    vi.stubEnv(PROJECTS_CONFIG_PATH_ENV, "/tmp/x.yaml");
    expect(
      resolveConfigPath(PROJECTS_CONFIG_PATH_ENV, "projects.yaml"),
    ).toEqual({ path: "/tmp/x.yaml", explicit: true });
  });
});

describe("loadProjectRepos", () => {
  it("PROJECTS_CONFIG_PATHのファイルを読む", async () => {
    const file = path.join(dir, "projects.yaml");
    await writeFile(file, "projects:\n  - repo: a/b\n  - repo: c/d\n");
    vi.stubEnv(PROJECTS_CONFIG_PATH_ENV, file);
    expect(await loadProjectRepos()).toEqual(["a/b", "c/d"]);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it("指定先が存在しなければ空配列で警告する", async () => {
    vi.stubEnv(PROJECTS_CONFIG_PATH_ENV, path.join(dir, "missing.yaml"));
    expect(await loadProjectRepos()).toEqual([]);
    expect(console.warn).toHaveBeenCalled();
  });

  it("不正なYAMLは空配列でエラーログを出す", async () => {
    const file = path.join(dir, "bad.yaml");
    await writeFile(file, "projects: [unclosed\n");
    vi.stubEnv(PROJECTS_CONFIG_PATH_ENV, file);
    expect(await loadProjectRepos()).toEqual([]);
    expect(console.error).toHaveBeenCalled();
  });

  it("読み込み権限エラー等（ENOENT以外）はエラーログを出す", async () => {
    // ディレクトリをファイルとして読むとEISDIRになる。
    vi.stubEnv(PROJECTS_CONFIG_PATH_ENV, dir);
    expect(await loadProjectRepos()).toEqual([]);
    expect(console.error).toHaveBeenCalled();
  });
});

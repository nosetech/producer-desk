import { describe, expect, it } from "vitest";
import {
  STATUS_CLOSED,
  STATUS_IN_PROGRESS,
  STATUS_IN_REVIEW,
  STATUS_NEEDS_HUMAN_DECISION,
  STATUS_TODO,
  projectDotColorVar,
  statusMeta,
} from "./status";

describe("projectDotColorVar", () => {
  it("完了は未着手と同じグレーにする", () => {
    expect(projectDotColorVar(STATUS_CLOSED)).toBe("--accent-gray");
  });

  it("他の4状態は従来の色を返す", () => {
    expect(projectDotColorVar(STATUS_TODO)).toBe("--accent-gray");
    expect(projectDotColorVar(STATUS_IN_PROGRESS)).toBe("--accent-blue");
    expect(projectDotColorVar(STATUS_NEEDS_HUMAN_DECISION)).toBe(
      "--accent-amber",
    );
    expect(projectDotColorVar(STATUS_IN_REVIEW)).toBe("--accent-purple");
  });

  it("未知ラベルはグレーにする", () => {
    expect(projectDotColorVar("unknown")).toBe("--accent-gray");
  });

  it("共有のstatusMetaでは完了が緑のまま", () => {
    expect(statusMeta(STATUS_CLOSED).colorVar).toBe("--accent-green");
  });
});

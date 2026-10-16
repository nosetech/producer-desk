import { describe, expect, it } from "vitest";
import { DIAG_META, TONE_VARS } from "./dispatchDiagnosis";
import { failureMessage } from "./jobs";
import type { DispatchState } from "./types";

describe("dispatchDiagnosis", () => {
  it("全ての診断状態に表示定義と配色がある", () => {
    const states: DispatchState[] = [
      "running",
      "queued",
      "completed",
      "not_dispatched",
      "orphaned_in_progress",
      "not_managed",
    ];
    for (const s of states) {
      expect(DIAG_META[s].label).not.toBe("");
      expect(TONE_VARS[DIAG_META[s].tone].color).toMatch(/^--/);
    }
  });

  it("再実行ジョブの失敗文言にissueと操作名が入る", () => {
    expect(
      failureMessage({
        repo: "nosetech/producer-desk",
        number: 7,
        kind: "rerun",
      }),
    ).toBe("producer-desk #7 の指示の再実行に失敗しました。");
  });
});

import { describe, expect, it } from "vitest";
import { checkPrompt, diffLines } from "./promptEditor";

const prompt = {
  required_tokens: [{ token: "<!-- marker -->", reason: "r" }],
  placeholders: ["repo", "issue_number"],
};

describe("checkPrompt", () => {
  it("必須トークンとプレースホルダが満たされていればok", () => {
    const r = checkPrompt(prompt, "{repo}#{issue_number} <!-- marker -->");
    expect(r).toEqual({ missing: [], unknown: [], empty: false, ok: true });
  });

  it("欠けた必須トークンを列挙する", () => {
    const r = checkPrompt(prompt, "本文のみ");
    expect(r.missing).toEqual(["<!-- marker -->"]);
    expect(r.ok).toBe(false);
  });

  it("未知のプレースホルダを重複なく列挙する", () => {
    const r = checkPrompt(prompt, "{foo} {foo} {bar} <!-- marker -->");
    expect(r.unknown).toEqual(["foo", "bar"]);
    expect(r.ok).toBe(false);
  });

  it("JSON例示の波括弧はプレースホルダとみなさない", () => {
    const r = checkPrompt(prompt, '{"used": true} <!-- marker -->');
    expect(r.unknown).toEqual([]);
    expect(r.ok).toBe(true);
  });

  it("空文字は保存不可", () => {
    expect(checkPrompt({ ...prompt, required_tokens: [] }, "  ").ok).toBe(
      false,
    );
  });
});

describe("diffLines", () => {
  it("同一内容は全行が共通", () => {
    expect(diffLines("a\nb", "a\nb")).toEqual([
      [" ", "a"],
      [" ", "b"],
    ]);
  });

  it("追加行と削除行を検出する", () => {
    expect(diffLines("a\nb\nc", "a\nx\nc")).toEqual([
      [" ", "a"],
      ["-", "b"],
      ["+", "x"],
      [" ", "c"],
    ]);
  });
});

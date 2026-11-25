import { describe, expect, it } from "vitest";
import {
  MAX_SNIPPET_BODY_LENGTH,
  MAX_SNIPPET_TITLE_LENGTH,
  firstLine,
  insertAtCursor,
  moveItem,
  charCount,
  checkSnippetDraft,
} from "./snippets";

describe("insertAtCursor", () => {
  it("カーソル位置に挿入し、カーソルを挿入文の末尾へ移す", () => {
    expect(insertAtCursor("abcd", 2, 2, "XY")).toEqual({
      text: "abXYcd",
      cursor: 4,
    });
  });

  it("範囲選択中は選択範囲を置換する", () => {
    expect(insertAtCursor("hello world", 6, 11, "there")).toEqual({
      text: "hello there",
      cursor: 11,
    });
  });

  it("空文字・先頭・末尾にも挿入できる", () => {
    expect(insertAtCursor("", 0, 0, "x")).toEqual({ text: "x", cursor: 1 });
    expect(insertAtCursor("ab", 0, 0, "x")).toEqual({ text: "xab", cursor: 1 });
    expect(insertAtCursor("ab", 2, 2, "x")).toEqual({ text: "abx", cursor: 3 });
  });

  it("範囲外・逆転した位置は丸める", () => {
    expect(insertAtCursor("ab", 10, 20, "x")).toEqual({
      text: "abx",
      cursor: 3,
    });
    expect(insertAtCursor("abcd", 3, 1, "x")).toEqual({
      text: "abcxd",
      cursor: 4,
    });
    expect(insertAtCursor("ab", -1, -1, "x")).toEqual({
      text: "xab",
      cursor: 1,
    });
  });

  it("/modelディレクティブ行の後ろにも通常どおり挿入される", () => {
    const text = "/model claude_code\n\n";
    expect(insertAtCursor(text, text.length, text.length, "進めて")).toEqual({
      text: "/model claude_code\n\n進めて",
      cursor: text.length + 3,
    });
  });
});

describe("checkSnippetDraft", () => {
  it("有効な入力ではエラーなし", () => {
    expect(checkSnippetDraft("方針OK", "この方針で進めて").ok).toBe(true);
    const atLimit = checkSnippetDraft(
      "x".repeat(MAX_SNIPPET_TITLE_LENGTH),
      "y".repeat(MAX_SNIPPET_BODY_LENGTH),
    );
    expect(atLimit.ok).toBe(true);
    expect(atLimit.titleLength).toBe(MAX_SNIPPET_TITLE_LENGTH);
  });

  it("空・上限超過を検出する", () => {
    const empty = checkSnippetDraft(" ", " ");
    expect(empty.titleError).toBe("タイトルを入力してください");
    expect(empty.bodyError).toBe("本文を入力してください");
    const over = checkSnippetDraft(
      "x".repeat(MAX_SNIPPET_TITLE_LENGTH + 1),
      "y".repeat(MAX_SNIPPET_BODY_LENGTH + 1),
    );
    expect(over.ok).toBe(false);
    expect(over.titleError).toBe(
      "タイトルは50文字以内にしてください（現在 51文字）",
    );
    expect(over.bodyError).toBe(
      "本文は2,000文字以内にしてください（現在 2,001文字）",
    );
  });

  it("サロゲートペアは1文字として数える", () => {
    expect(charCount("😀a")).toBe(2);
  });
});

describe("firstLine / moveItem", () => {
  it("本文の先頭1行を返す", () => {
    expect(firstLine("\n \n一行目\n二行目")).toBe("一行目");
  });

  it("要素を前後に移動し、範囲外は変更しない", () => {
    expect(moveItem(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
    expect(moveItem(["a", "b", "c"], 1, 1)).toEqual(["a", "c", "b"]);
    const same = ["a", "b"];
    expect(moveItem(same, 0, -1)).toBe(same);
    expect(moveItem(same, 1, 1)).toBe(same);
  });
});

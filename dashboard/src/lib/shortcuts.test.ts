import { describe, expect, it } from "vitest";
import {
  isSameScreen,
  resolveShortcutHref,
  shouldIgnoreShortcut,
} from "./shortcuts";

const base = { key: "d", target: { tagName: "DIV" } };

describe("shouldIgnoreShortcut", () => {
  it("通常要素では無視しない", () => {
    expect(shouldIgnoreShortcut(base)).toBe(false);
  });
  it.each(["INPUT", "TEXTAREA", "SELECT"])("%sでは無視する", (tagName) => {
    expect(shouldIgnoreShortcut({ ...base, target: { tagName } })).toBe(true);
  });
  it("contentEditableでは無視する", () => {
    expect(
      shouldIgnoreShortcut({
        ...base,
        target: { tagName: "DIV", isContentEditable: true },
      }),
    ).toBe(true);
  });
  it("IME変換中は無視する", () => {
    expect(shouldIgnoreShortcut({ ...base, isComposing: true })).toBe(true);
    expect(shouldIgnoreShortcut({ ...base, keyCode: 229 })).toBe(true);
  });
  it.each(["ctrlKey", "metaKey", "altKey", "shiftKey"])(
    "%s付きは無視する",
    (mod) => {
      expect(shouldIgnoreShortcut({ ...base, [mod]: true })).toBe(true);
    },
  );
  it("repeatは無視する", () => {
    expect(shouldIgnoreShortcut({ ...base, repeat: true })).toBe(true);
  });
  it("処理済みイベントは無視する", () => {
    expect(shouldIgnoreShortcut({ ...base, defaultPrevented: true })).toBe(
      true,
    );
  });
  it("モーダル表示中は無視する", () => {
    expect(shouldIgnoreShortcut(base, true)).toBe(true);
  });
});

describe("resolveShortcutHref", () => {
  it("d/i/pを遷移先に解決する（大文字小文字不問）", () => {
    expect(resolveShortcutHref("d")).toBe("/");
    expect(resolveShortcutHref("I")).toBe("/projects");
    expect(resolveShortcutHref("p")).toBe("/prompts");
  });
  it("未割り当てのキーはnull", () => {
    expect(resolveShortcutHref("x")).toBeNull();
  });
});

describe("isSameScreen", () => {
  it("同じ画面を判定する", () => {
    expect(isSameScreen("/", "/")).toBe(true);
    expect(isSameScreen("/projects/foo", "/projects")).toBe(true);
    expect(isSameScreen("/prompts", "/projects")).toBe(false);
    expect(isSameScreen("/projects", "/")).toBe(false);
  });
});

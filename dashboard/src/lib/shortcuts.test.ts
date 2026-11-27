import { describe, expect, it } from "vitest";
import {
  ISSUE_LIST_SHORTCUTS,
  NAV_SHORTCUTS,
  ariaKeyShortcuts,
  cursorOrder,
  isSameScreen,
  relocateCursor,
  resolveIssueListAction,
  resolveShortcutHref,
  shouldIgnoreShortcut,
  stepIndex,
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
  it("d/i/p/sを遷移先に解決する（大文字小文字不問）", () => {
    expect(resolveShortcutHref("d")).toBe("/");
    expect(resolveShortcutHref("I")).toBe("/projects");
    expect(resolveShortcutHref("p")).toBe("/prompts");
    expect(resolveShortcutHref("S")).toBe("/snippets");
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

describe("shouldIgnoreShortcut（オプション）", () => {
  it("allowShiftでShift付きを許可する", () => {
    expect(
      shouldIgnoreShortcut({ ...base, key: "H", shiftKey: true }, false, {
        allowShift: true,
      }),
    ).toBe(false);
  });
  it("allowRepeatで押しっぱなしを許可する", () => {
    expect(
      shouldIgnoreShortcut({ ...base, key: "j", repeat: true }, false, {
        allowRepeat: true,
      }),
    ).toBe(false);
  });
  it("許可しても入力中・IME・他の修飾キー・モーダルは無視する", () => {
    const opts = { allowShift: true, allowRepeat: true };
    const ev = { ...base, key: "H", shiftKey: true };
    expect(
      shouldIgnoreShortcut(
        { ...ev, target: { tagName: "INPUT" } },
        false,
        opts,
      ),
    ).toBe(true);
    expect(
      shouldIgnoreShortcut({ ...ev, isComposing: true }, false, opts),
    ).toBe(true);
    expect(shouldIgnoreShortcut({ ...ev, ctrlKey: true }, false, opts)).toBe(
      true,
    );
    expect(shouldIgnoreShortcut(ev, true, opts)).toBe(true);
  });
  it("Shift付きのH/Lは既定（画面遷移ショートカット）では無視される", () => {
    for (const key of ["H", "L"]) {
      expect(shouldIgnoreShortcut({ ...base, key, shiftKey: true })).toBe(true);
    }
  });
});

describe("resolveIssueListAction", () => {
  it("各キーを動作に解決する（大文字小文字を区別）", () => {
    expect(resolveIssueListAction("h")).toBe("prevProject");
    expect(resolveIssueListAction("l")).toBe("nextProject");
    expect(resolveIssueListAction("j")).toBe("cursorDown");
    expect(resolveIssueListAction("k")).toBe("cursorUp");
    expect(resolveIssueListAction("x")).toBe("toggleSelect");
    expect(resolveIssueListAction("Escape")).toBe("clearSelection");
    expect(resolveIssueListAction("H")).toBe("prevFilter");
    expect(resolveIssueListAction("L")).toBe("nextFilter");
    expect(resolveIssueListAction("Enter")).toBe("activate");
  });
  it("Shift付きの英小文字は大文字として扱う", () => {
    expect(resolveIssueListAction("h", true)).toBe("prevFilter");
    expect(resolveIssueListAction("l", true)).toBe("nextFilter");
    expect(resolveIssueListAction("j", true)).toBeNull();
  });
  it("未割り当てのキーはnull", () => {
    expect(resolveIssueListAction("d")).toBeNull();
    expect(resolveIssueListAction("J")).toBeNull();
  });
  it("画面遷移ショートカット（d/i/p/s）と重ならない", () => {
    const nav = NAV_SHORTCUTS.map((s) => s.key as string);
    for (const s of ISSUE_LIST_SHORTCUTS) {
      expect(nav).not.toContain(s.key.toLowerCase());
    }
  });
});

describe("ariaKeyShortcuts", () => {
  it("Shift付きのキーはShift+で表す", () => {
    expect(ariaKeyShortcuts("prevProject", "nextProject")).toBe("h l");
    expect(ariaKeyShortcuts("prevFilter", "nextFilter")).toBe(
      "Shift+H Shift+L",
    );
  });
});

describe("stepIndex", () => {
  it("前後へ進め、端で止まる", () => {
    expect(stepIndex(1, 1, 3)).toBe(2);
    expect(stepIndex(2, 1, 3)).toBe(2);
    expect(stepIndex(1, -1, 3)).toBe(0);
    expect(stepIndex(0, -1, 3)).toBe(0);
  });
  it("未選択なら下向きは先頭、上向きは末尾から", () => {
    expect(stepIndex(-1, 1, 3)).toBe(0);
    expect(stepIndex(-1, -1, 3)).toBe(2);
  });
  it("範囲外のcurrentも未選択扱い", () => {
    expect(stepIndex(5, 1, 3)).toBe(0);
  });
  it("空ならnull", () => {
    expect(stepIndex(0, 1, 0)).toBeNull();
  });
});

describe("relocateCursor", () => {
  it("残っていればそのまま", () => {
    expect(relocateCursor(2, [1, 2, 3], [3, 2])).toBe(2);
  });
  it("消えたら後ろの最も近い行、無ければ前の行へ寄せる", () => {
    expect(relocateCursor(2, [1, 2, 3, 4], [1, 4])).toBe(4);
    expect(relocateCursor(4, [1, 2, 3, 4], [1, 2])).toBe(2);
  });
  it("寄せる先が無ければnull", () => {
    expect(relocateCursor(2, [1, 2], [])).toBeNull();
    expect(relocateCursor(2, [], [1])).toBeNull();
    expect(relocateCursor(null, [1], [1])).toBeNull();
  });
});

describe("shouldIgnoreShortcut（Enter、issue #339）", () => {
  const enter = { key: "Enter", target: { tagName: "DIV" } };
  const opts = { ignoreOnInteractive: true };
  it("通常要素では無視しない", () => {
    expect(shouldIgnoreShortcut(enter, false, opts)).toBe(false);
  });
  it.each(["BUTTON", "A", "SUMMARY"])(
    "%sにフォーカスがあるときは無視する",
    (tagName) => {
      expect(
        shouldIgnoreShortcut({ ...enter, target: { tagName } }, false, opts),
      ).toBe(true);
    },
  );
  it("role=buttonの要素にフォーカスがあるときは無視する", () => {
    const target = {
      tagName: "DIV",
      getAttribute: (n: string) => (n === "role" ? "button" : null),
    };
    expect(shouldIgnoreShortcut({ ...enter, target }, false, opts)).toBe(true);
  });
  it("オプションが無ければボタン上でも無視しない（既存のショートカット）", () => {
    expect(
      shouldIgnoreShortcut({ ...base, target: { tagName: "BUTTON" } }),
    ).toBe(false);
  });
  it("入力中・IME変換中・押しっぱなし・モーダル表示中は無視する", () => {
    expect(
      shouldIgnoreShortcut(
        { ...enter, target: { tagName: "TEXTAREA" } },
        false,
        opts,
      ),
    ).toBe(true);
    expect(
      shouldIgnoreShortcut({ ...enter, isComposing: true }, false, opts),
    ).toBe(true);
    expect(shouldIgnoreShortcut({ ...enter, repeat: true }, false, opts)).toBe(
      true,
    );
    expect(shouldIgnoreShortcut(enter, true, opts)).toBe(true);
  });
});

describe("cursorOrder（issue #339）", () => {
  it("inbox項目 → issue一覧の順に並べる", () => {
    expect(cursorOrder([30, 20], [5, 3, 1], true)).toEqual([30, 20, 5, 3, 1]);
  });
  it("inboxが折りたたまれている間はinbox項目を含めない", () => {
    expect(cursorOrder([30, 20], [5, 3], false)).toEqual([5, 3]);
  });
  it("重複する番号はissue一覧側に残す", () => {
    expect(cursorOrder([30, 5], [5, 3], true)).toEqual([30, 5, 3]);
  });
  it("inboxの最後からjでissue一覧の先頭へ、issue一覧の先頭からkでinboxの最後へ移る", () => {
    const order = cursorOrder([30, 20], [5, 3], true);
    expect(order[stepIndex(order.indexOf(20), 1, order.length)!]).toBe(5);
    expect(order[stepIndex(order.indexOf(5), -1, order.length)!]).toBe(20);
  });
  it("端では止まる", () => {
    const order = cursorOrder([30], [5], true);
    expect(order[stepIndex(0, -1, order.length)!]).toBe(30);
    expect(order[stepIndex(1, 1, order.length)!]).toBe(5);
  });
  it("inboxを折りたたむと、inbox上のカーソルはissue一覧の先頭へ寄せる", () => {
    const prev = cursorOrder([30, 20], [5, 3], true);
    const next = cursorOrder([30, 20], [5, 3], false);
    expect(relocateCursor(20, prev, next)).toBe(5);
  });
  it("折りたたみで寄せる先が無ければ未選択に戻す", () => {
    const prev = cursorOrder([30], [], true);
    const next = cursorOrder([30], [], false);
    expect(relocateCursor(30, prev, next)).toBeNull();
  });
});

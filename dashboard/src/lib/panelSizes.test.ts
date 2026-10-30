import { describe, expect, it } from "vitest";
import {
  MIN_PANEL_SIZE,
  VIEWPORT_MARGIN,
  clampSize,
  maxPanelSize,
  maxPanelSizeCss,
  parsePanelSizes,
} from "./panelSizes";

describe("clampSize", () => {
  it("最小サイズを下回らない", () => {
    expect(clampSize(10, 1000)).toBe(MIN_PANEL_SIZE);
  });

  it("viewport より大きくならない", () => {
    expect(clampSize(5000, 800)).toBe(776);
  });

  it("範囲内の値は丸めてそのまま返す", () => {
    expect(clampSize(400.4, 1000)).toBe(400);
  });

  it("viewport が極端に小さくても最小サイズを維持する", () => {
    expect(clampSize(300, 100)).toBe(MIN_PANEL_SIZE);
  });
});

describe("parsePanelSizes", () => {
  it("欠損・不正JSONは空（既定サイズ）", () => {
    expect(parsePanelSizes(null)).toEqual({});
    expect(parsePanelSizes("")).toEqual({});
    expect(parsePanelSizes("{broken")).toEqual({});
    expect(parsePanelSizes("[1,2]")).toEqual({});
    expect(parsePanelSizes("null")).toEqual({});
  });

  it("正しい値を読み込む", () => {
    const raw = JSON.stringify({
      composerPanel: { width: 700, height: 500.4 },
      composerQuote: { height: 300 },
    });
    expect(parsePanelSizes(raw)).toEqual({
      composerPanel: { width: 700, height: 500 },
      composerQuote: { height: 300 },
    });
  });

  it("不正なキーだけを捨て、ほかのキーは残す", () => {
    const raw = JSON.stringify({
      composerPanel: { width: "wide" },
      composerQuote: { height: 10 },
      composerTextarea: { height: 300 },
      commentViewer: { width: 640, height: 360 },
      unknown: { width: 500 },
    });
    expect(parsePanelSizes(raw)).toEqual({
      commentViewer: { width: 640, height: 360 },
    });
  });

  it("上端位置を読み込み、不正な値のエントリは捨てる", () => {
    expect(
      parsePanelSizes(
        JSON.stringify({ composerPanel: { height: 400, top: 40.4 } }),
      ),
    ).toEqual({ composerPanel: { height: 400, top: 40 } });
    expect(
      parsePanelSizes(
        JSON.stringify({ composerPanel: { height: 400, top: -3 } }),
      ),
    ).toEqual({});
  });

  it("幅も高さもないエントリは捨てる", () => {
    expect(parsePanelSizes(JSON.stringify({ composerPanel: {} }))).toEqual({});
  });
});

describe("maxPanelSize", () => {
  it("viewport から余白を引いた値を返す", () => {
    expect(maxPanelSize(800)).toBe(800 - VIEWPORT_MARGIN);
  });

  it("他の要素が占める分も差し引く", () => {
    expect(maxPanelSize(800, 100)).toBe(800 - VIEWPORT_MARGIN - 100);
  });

  it("小さい画面では最小値を優先する", () => {
    expect(maxPanelSize(100)).toBe(MIN_PANEL_SIZE);
    expect(maxPanelSize(300, 250)).toBe(MIN_PANEL_SIZE);
  });
});

describe("maxPanelSizeCss", () => {
  it("幅は vw、高さは dvh で同じ余白を使う", () => {
    expect(maxPanelSizeCss("width")).toBe("max(120px, calc(100vw - 24px))");
    expect(maxPanelSizeCss("height", 80)).toBe(
      "max(120px, calc(100dvh - 104px))",
    );
  });
});

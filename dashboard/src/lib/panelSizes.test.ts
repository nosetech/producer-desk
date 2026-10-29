import { describe, expect, it } from "vitest";
import { MIN_PANEL_SIZE, clampSize, parsePanelSizes } from "./panelSizes";

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
      composerTextarea: { height: NaN },
      commentViewer: { width: 640, height: 360 },
      unknown: { width: 500 },
    });
    expect(parsePanelSizes(raw)).toEqual({
      commentViewer: { width: 640, height: 360 },
    });
  });

  it("幅も高さもないエントリは捨てる", () => {
    expect(parsePanelSizes(JSON.stringify({ composerPanel: {} }))).toEqual({});
  });
});

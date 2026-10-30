import { describe, expect, it } from "vitest";
import {
  EDGE_ZONE,
  clampTop,
  detectEdges,
  edgeCursor,
  resizeByEdges,
} from "./edgeResize";
import { MIN_PANEL_SIZE } from "./panelSizes";

const rect = { left: 100, right: 500, top: 50, bottom: 450 };

describe("detectEdges", () => {
  it("中央は辺ではない", () => {
    expect(detectEdges(rect, 300, 250)).toEqual([]);
  });

  it("各辺と角を判定する", () => {
    expect(detectEdges(rect, 100 + 2, 250)).toEqual(["left"]);
    expect(detectEdges(rect, 500 - 2, 250)).toEqual(["right"]);
    expect(detectEdges(rect, 300, 50 + 2)).toEqual(["top"]);
    expect(detectEdges(rect, 300, 450 - 2)).toEqual(["bottom"]);
    expect(detectEdges(rect, 500 - 1, 450 - 1)).toEqual(["bottom", "right"]);
    expect(detectEdges(rect, 101, 51)).toEqual(["top", "left"]);
  });

  it("辺の幅を超えた内側と、枠の外は対象外", () => {
    expect(detectEdges(rect, 100 + EDGE_ZONE + 1, 250)).toEqual([]);
    expect(detectEdges(rect, 99, 250)).toEqual([]);
    expect(detectEdges(rect, 300, 451)).toEqual([]);
  });
});

describe("edgeCursor", () => {
  it("辺と角のカーソルを返す", () => {
    expect(edgeCursor([])).toBe("");
    expect(edgeCursor(["left"])).toBe("w-resize");
    expect(edgeCursor(["bottom"])).toBe("s-resize");
    expect(edgeCursor(["top", "right"])).toBe("ne-resize");
    expect(edgeCursor(["bottom", "left"])).toBe("sw-resize");
  });
});

const base = {
  viewportWidth: 1200,
  viewportHeight: 900,
  symmetricY: false,
  bounds: { top: 12, bottom: 888 },
};
const start = { width: 500, height: 400, top: 100 };

describe("resizeByEdges", () => {
  it("左右の辺は反対側も動くので幅が2倍の量で変わる", () => {
    expect(resizeByEdges(start, ["right"], 30, 0, base).width).toBe(560);
    expect(resizeByEdges(start, ["left"], -30, 0, base).width).toBe(560);
    expect(resizeByEdges(start, ["left"], 30, 0, base).width).toBe(440);
  });

  it("下の辺は高さだけ変わり、上端は動かない", () => {
    const r = resizeByEdges(start, ["bottom"], 0, 50, base);
    expect(r).toEqual({ width: 500, height: 450, top: 100 });
  });

  it("上の辺は下端を保ったまま上端位置と高さが変わる", () => {
    const r = resizeByEdges(start, ["top"], 0, -50, base);
    expect(r).toEqual({ width: 500, height: 450, top: 50 });
  });

  it("上の辺は親の上端を越えない", () => {
    const r = resizeByEdges(start, ["top"], 0, -500, base);
    expect(r.top).toBe(12);
    expect(r.height).toBe(488);
  });

  it("下の辺は親の下端を越えない", () => {
    const r = resizeByEdges(start, ["bottom"], 0, 800, base);
    expect(r.height).toBe(888 - 100);
  });

  it("最小サイズより小さくならない", () => {
    const r = resizeByEdges(start, ["top"], 0, 1000, base);
    expect(r.height).toBe(MIN_PANEL_SIZE);
    expect(r.top).toBe(100 + 400 - MIN_PANEL_SIZE);
    expect(resizeByEdges(start, ["left"], 1000, 0, base).width).toBe(
      MIN_PANEL_SIZE,
    );
  });

  it("viewport を超えない", () => {
    expect(resizeByEdges(start, ["right"], 5000, 0, base).width).toBe(1176);
  });

  it("角は幅と高さを同時に変える", () => {
    const r = resizeByEdges(start, ["bottom", "right"], 10, 20, base);
    expect(r).toEqual({ width: 520, height: 420, top: 100 });
  });

  it("対称モードでは上下とも2倍の量で変わり、上端は動かない", () => {
    const opts = { ...base, symmetricY: true, bounds: undefined };
    expect(resizeByEdges(start, ["bottom"], 0, 25, opts).height).toBe(450);
    expect(resizeByEdges(start, ["top"], 0, -25, opts).height).toBe(450);
    expect(resizeByEdges(start, ["top"], 0, -25, opts).top).toBe(100);
  });

  it("対称モードでも他の要素の分だけ上限が下がる", () => {
    const opts = {
      ...base,
      symmetricY: true,
      bounds: undefined,
      reservedHeight: 200,
    };
    expect(resizeByEdges(start, ["bottom"], 0, 5000, opts).height).toBe(
      900 - 24 - 200,
    );
  });
});

describe("clampTop", () => {
  it("親の範囲に収める", () => {
    const bounds = { top: 12, bottom: 800 };
    expect(clampTop(50, 400, bounds)).toBe(50);
    expect(clampTop(-5, 400, bounds)).toBe(12);
    expect(clampTop(700, 400, bounds)).toBe(400);
  });
});

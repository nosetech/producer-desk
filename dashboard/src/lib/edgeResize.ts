import { MIN_PANEL_SIZE, clampSize } from "./panelSizes";

export type Edge = "top" | "bottom" | "left" | "right";

// `data-edge="top left"` のような属性値を辺の配列にする（不明な値は無視する）。
export function parseEdges(value: string | undefined): Edge[] {
  return (value ?? "")
    .split(" ")
    .filter((v): v is Edge => ["top", "bottom", "left", "right"].includes(v));
}

export type EdgeStart = { width: number; height: number; top: number };

type EdgeOptions = {
  viewportWidth: number;
  viewportHeight: number;
  // 高さの上限から差し引く、同じ親の中で他の要素が占める分。
  reservedHeight?: number;
  // true: 上下とも中央から対称に広がる。false: 下の辺は高さのみ、上の辺は上端位置も動く。
  symmetricY: boolean;
  // symmetricY が false のときの、親の中で上端・下端が動ける範囲。
  bounds?: { top: number; bottom: number };
};

// 辺のドラッグ量（dx, dy）から新しいサイズ・上端位置を求める。左右は常に中央から対称に広がる。
export function resizeByEdges(
  start: EdgeStart,
  edges: readonly Edge[],
  dx: number,
  dy: number,
  opts: EdgeOptions,
): EdgeStart {
  const sx = edges.includes("right") ? 1 : edges.includes("left") ? -1 : 0;
  const sy = edges.includes("bottom") ? 1 : edges.includes("top") ? -1 : 0;
  const reserved = opts.reservedHeight ?? 0;

  const width = sx
    ? clampSize(start.width + sx * 2 * dx, opts.viewportWidth)
    : start.width;

  if (!sy) return { width, height: start.height, top: start.top };

  if (opts.symmetricY) {
    const height = clampSize(
      start.height + sy * 2 * dy,
      opts.viewportHeight,
      reserved,
    );
    return { width, height, top: start.top };
  }

  const bottom = start.top + start.height;
  const bounds = opts.bounds;
  if (sy > 0) {
    let height = clampSize(start.height + dy, opts.viewportHeight, reserved);
    if (bounds) {
      height = Math.max(
        MIN_PANEL_SIZE,
        Math.min(height, bounds.bottom - start.top),
      );
    }
    return { width, height, top: start.top };
  }
  let height = clampSize(start.height - dy, opts.viewportHeight, reserved);
  if (bounds) {
    height = Math.max(MIN_PANEL_SIZE, Math.min(height, bottom - bounds.top));
  }
  return { width, height, top: bottom - height };
}

// 保存済みの上端位置を、親の高さに収まる範囲へ寄せる。
export function clampTop(
  top: number,
  height: number,
  bounds: { top: number; bottom: number },
): number {
  return Math.max(bounds.top, Math.min(top, bounds.bottom - height));
}

// 返信UI・コメント全文モーダルのユーザー指定サイズ。localStorage に1つのJSONで保存する。
export type PanelKey =
  "composerPanel" | "composerQuote" | "composerTextarea" | "commentViewer";

export type PanelSize = { width?: number; height?: number };

export type PanelSizes = Partial<Record<PanelKey, PanelSize>>;

export const PANEL_KEYS: readonly PanelKey[] = [
  "composerPanel",
  "composerQuote",
  "composerTextarea",
  "commentViewer",
];

export const PANEL_STORAGE_KEY = "producer-desk:panel-sizes";

// これより小さくはできない（操作不能になるのを防ぐ）。
export const MIN_PANEL_SIZE = 120;

// viewport に対する余白。ウィンドウより大きくならないよう上限を設ける。
const VIEWPORT_MARGIN = 24;

// 値を最小サイズ〜viewport 由来の上限に収める。上限が最小値を下回る小さい画面では最小値を優先する。
export function clampSize(value: number, viewportSize: number): number {
  const max = Math.max(MIN_PANEL_SIZE, viewportSize - VIEWPORT_MARGIN);
  return Math.min(max, Math.max(MIN_PANEL_SIZE, Math.round(value)));
}

function parseSize(raw: unknown): PanelSize | null {
  if (typeof raw !== "object" || raw === null) return null;
  const record = raw as Record<string, unknown>;
  const size: PanelSize = {};
  for (const axis of ["width", "height"] as const) {
    const value = record[axis];
    if (value === undefined) continue;
    if (typeof value !== "number" || !Number.isFinite(value)) return null;
    if (value < MIN_PANEL_SIZE) return null;
    size[axis] = Math.round(value);
  }
  return size.width === undefined && size.height === undefined ? null : size;
}

// localStorage の保存値を検証する。不正・欠損なら（該当キーを除いて）既定サイズ扱い。
export function parsePanelSizes(raw: string | null): PanelSizes {
  if (!raw) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return {};
    const record = parsed as Record<string, unknown>;
    const result: PanelSizes = {};
    for (const key of PANEL_KEYS) {
      const size = parseSize(record[key]);
      if (size) result[key] = size;
    }
    return result;
  } catch {
    return {};
  }
}

export function loadPanelSizes(): PanelSizes {
  try {
    return parsePanelSizes(window.localStorage.getItem(PANEL_STORAGE_KEY));
  } catch {
    return {};
  }
}

export function savePanelSize(key: PanelKey, size: PanelSize): void {
  try {
    const next = { ...loadPanelSizes(), [key]: size };
    window.localStorage.setItem(PANEL_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // 保存できなくても表示には影響しない
  }
}

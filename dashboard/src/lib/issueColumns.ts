// issue一覧（PC幅の表形式）の列幅。タイトル列は残り幅を吸収するため対象外。
export type ResizableColumn =
  "number" | "status" | "comments" | "updated" | "actions";

export type ColumnWidths = Record<ResizableColumn, number>;

export const COLUMN_ORDER: readonly ResizableColumn[] = [
  "number",
  "status",
  "comments",
  "updated",
  "actions",
];

export const DEFAULT_COLUMN_WIDTHS: ColumnWidths = {
  number: 58,
  status: 116,
  comments: 44,
  updated: 78,
  actions: 142,
};

export const MIN_COLUMN_WIDTHS: ColumnWidths = {
  number: 40,
  status: 80,
  comments: 32,
  updated: 56,
  actions: 142,
};

export const COLUMN_STORAGE_KEY = "producer-desk:issue-list-columns";

// 列間の gap（12px × 5）と行の左右 padding（16px × 2）、タイトル列に最低限残す幅。
const GRID_GAP = 12;
const GRID_COLUMN_COUNT = 6;
const ROW_PADDING = 32;
const MIN_TITLE_WIDTH = 160;

function maxTotalWidth(containerWidth: number): number {
  return (
    containerWidth -
    ROW_PADDING -
    GRID_GAP * (GRID_COLUMN_COUNT - 1) -
    MIN_TITLE_WIDTH
  );
}

function total(widths: ColumnWidths): number {
  return COLUMN_ORDER.reduce((sum, key) => sum + widths[key], 0);
}

// 指定列の幅を最小幅〜（コンテナ幅から算出した上限）の範囲に収めて返す。
// containerWidth が不明（0以下）のときは上限を設けない。
export function resizeColumn(
  widths: ColumnWidths,
  key: ResizableColumn,
  desired: number,
  containerWidth: number,
): ColumnWidths {
  const min = MIN_COLUMN_WIDTHS[key];
  let next = Math.max(min, Math.round(desired));
  if (containerWidth > 0) {
    const others = total(widths) - widths[key];
    const max = Math.max(min, maxTotalWidth(containerWidth) - others);
    next = Math.min(next, max);
  }
  return { ...widths, [key]: next };
}

// localStorage の保存値を検証する。不正・欠損なら既定幅を返す。
export function parseColumnWidths(raw: string | null): ColumnWidths {
  if (!raw) return { ...DEFAULT_COLUMN_WIDTHS };
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) {
      return { ...DEFAULT_COLUMN_WIDTHS };
    }
    const record = parsed as Record<string, unknown>;
    const result = { ...DEFAULT_COLUMN_WIDTHS };
    for (const key of COLUMN_ORDER) {
      const value = record[key];
      if (typeof value !== "number" || !Number.isFinite(value)) {
        return { ...DEFAULT_COLUMN_WIDTHS };
      }
      if (value < MIN_COLUMN_WIDTHS[key]) {
        return { ...DEFAULT_COLUMN_WIDTHS };
      }
      result[key] = Math.round(value);
    }
    return result;
  } catch {
    return { ...DEFAULT_COLUMN_WIDTHS };
  }
}

export function loadColumnWidths(): ColumnWidths {
  try {
    return parseColumnWidths(window.localStorage.getItem(COLUMN_STORAGE_KEY));
  } catch {
    return { ...DEFAULT_COLUMN_WIDTHS };
  }
}

export function saveColumnWidths(widths: ColumnWidths): void {
  try {
    window.localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(widths));
  } catch {
    // 保存できなくても表示には影響しない
  }
}

export function columnsToTemplate(widths: ColumnWidths): string {
  return `${widths.number}px minmax(0, 1fr) ${widths.status}px ${widths.comments}px ${widths.updated}px ${widths.actions}px`;
}

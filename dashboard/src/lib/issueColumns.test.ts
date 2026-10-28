import { describe, expect, it } from "vitest";
import {
  DEFAULT_COLUMN_WIDTHS,
  columnsToTemplate,
  parseColumnWidths,
  resizeColumn,
} from "./issueColumns";

describe("resizeColumn", () => {
  it("最小幅を下回らない", () => {
    const w = resizeColumn(DEFAULT_COLUMN_WIDTHS, "status", 10, 1200);
    expect(w.status).toBe(80);
  });

  it("合計幅がコンテナを超えないようクランプする", () => {
    const w = resizeColumn(DEFAULT_COLUMN_WIDTHS, "status", 5000, 900);
    const sum = Object.values(w).reduce((a, b) => a + b, 0);
    expect(sum + 32 + 12 * 5 + 160).toBeLessThanOrEqual(900);
    expect(w.status).toBeGreaterThan(DEFAULT_COLUMN_WIDTHS.status);
  });

  it("コンテナ幅が不明なら上限を設けない", () => {
    expect(resizeColumn(DEFAULT_COLUMN_WIDTHS, "updated", 400, 0).updated).toBe(
      400,
    );
  });
});

describe("parseColumnWidths", () => {
  it("欠損・不正値は既定幅", () => {
    expect(parseColumnWidths(null)).toEqual(DEFAULT_COLUMN_WIDTHS);
    expect(parseColumnWidths("{bad")).toEqual(DEFAULT_COLUMN_WIDTHS);
    expect(parseColumnWidths("[]")).toEqual(DEFAULT_COLUMN_WIDTHS);
    expect(
      parseColumnWidths(
        JSON.stringify({ ...DEFAULT_COLUMN_WIDTHS, status: "x" }),
      ),
    ).toEqual(DEFAULT_COLUMN_WIDTHS);
    expect(
      parseColumnWidths(
        JSON.stringify({ ...DEFAULT_COLUMN_WIDTHS, status: 1 }),
      ),
    ).toEqual(DEFAULT_COLUMN_WIDTHS);
  });

  it("正しい保存値は復元する", () => {
    const saved = { ...DEFAULT_COLUMN_WIDTHS, status: 150 };
    expect(parseColumnWidths(JSON.stringify(saved))).toEqual(saved);
  });
});

describe("columnsToTemplate", () => {
  it("既定幅は従来のgrid定義と一致する", () => {
    expect(columnsToTemplate(DEFAULT_COLUMN_WIDTHS)).toBe(
      "58px minmax(0, 1fr) 116px 44px 78px 142px",
    );
  });
});

import { describe, expect, it } from "vitest";
import {
  ATTACH_LIMITS,
  addFiles,
  attachKind,
  formatSize,
  namePastedFile,
  type AttachItem,
} from "./mediaAttach";

const MB = 1024 * 1024;

function fakeFile(name: string, size: number): File {
  const f = new File(["x"], name);
  Object.defineProperty(f, "size", { value: size });
  return f;
}

function seq() {
  let n = 0;
  return () => `a${++n}`;
}

describe("attachKind", () => {
  it("対応形式だけを画像・動画に分類する（svgは除外）", () => {
    expect(attachKind("a.PNG")).toBe("image");
    expect(attachKind("a.jpeg")).toBe("image");
    expect(attachKind("a.mov")).toBe("video");
    expect(attachKind("a.svg")).toBeNull();
    expect(attachKind("a.pdf")).toBeNull();
    expect(attachKind("noext")).toBeNull();
  });
});

describe("formatSize", () => {
  it("MB/KBで表示する", () => {
    expect(formatSize(12.4 * MB)).toBe("12.4MB");
    expect(formatSize(300)).toBe("1KB");
  });
});

describe("addFiles", () => {
  it("形式・サイズ・件数・合計の順に弾き、理由を返す", () => {
    const { items, errors } = addFiles(
      [],
      [
        fakeFile("ok.png", 1 * MB),
        fakeFile("report.pdf", 1),
        fakeFile("big.mp4", 11 * MB),
      ],
      seq(),
    );
    expect(items.map((x) => x.name)).toEqual(["ok.png"]);
    expect(errors).toEqual([
      { name: "report.pdf", reason: "対応していない形式です" },
      { name: "big.mp4", reason: "1ファイル10MBを超えています（11.0MB）" },
    ]);
  });

  it("件数の上限を超えた分を弾く", () => {
    const files = Array.from({ length: ATTACH_LIMITS.count + 1 }, (_, i) =>
      fakeFile(`${i}.png`, 1),
    );
    const { items, errors } = addFiles([], files, seq());
    expect(items).toHaveLength(ATTACH_LIMITS.count);
    expect(errors[0].reason).toBe("一度に添付できるのは10件までです");
  });

  it("合計50MBを超える分を弾く", () => {
    const current: AttachItem[] = Array.from({ length: 5 }, (_, i) => ({
      id: `c${i}`,
      file: fakeFile(`${i}.mp4`, 9.5 * MB),
      name: `${i}.mp4`,
      size: 9.5 * MB,
      kind: "video",
    }));
    const { items, errors } = addFiles(
      current,
      [fakeFile("w.webm", 5 * MB)],
      seq(),
    );
    expect(items).toHaveLength(5);
    expect(errors[0].reason).toBe(
      "合計50MBを超えるため追加できません（残り 2.5MB）",
    );
  });
});

describe("namePastedFile", () => {
  it("汎用名のスクリーンショットを時刻入りの名前にする", () => {
    const f = namePastedFile(
      new File(["x"], "image.png", { type: "image/png" }),
      new Date(2026, 0, 1, 9, 5, 7),
    );
    expect(f.name).toBe("スクリーンショット 090507.png");
    expect(namePastedFile(new File(["x"], "a.png")).name).toBe("a.png");
  });
});

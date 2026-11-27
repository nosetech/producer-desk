/**
 * 返信欄・新規タスク作成での画像・動画の添付（issue #301）。
 *
 * 形式・上限はオーケストレータ側（`orchestrator/orchestrator/media_uploads.py`）と同じ値にする。
 * svgは`gh --attach`では付けられるが、スクリプトを含められる（XSS）ため除外する。
 */

const MB = 1024 * 1024;

export const ATTACH_LIMITS = {
  file: 10 * MB,
  count: 10,
  total: 50 * MB,
} as const;

export type AttachKind = "image" | "video";

const OK_TYPES: Record<string, AttachKind> = {
  png: "image",
  jpg: "image",
  jpeg: "image",
  gif: "image",
  mp4: "video",
  mov: "video",
  webm: "video",
};

export const ATTACH_ACCEPT =
  ".png,.jpg,.jpeg,.gif,.mp4,.mov,.webm,image/png,image/jpeg,image/gif,video/mp4,video/quicktime,video/webm";
export const ATTACH_HINT =
  "png/jpg/gif・mp4/mov/webm、1件10MBまで・最大10件（合計50MB）";
export const ATTACH_DROP_SUB = "png/jpg/gif・mp4/mov/webm";
export const ATTACH_PLACEHOLDER_SUFFIX =
  "\n画像・動画はドロップや貼り付けでも添付できます";

export function formatSize(bytes: number): string {
  return bytes >= MB
    ? `${(bytes / MB).toFixed(1)}MB`
    : `${Math.max(1, Math.round(bytes / 1024))}KB`;
}

export function attachKind(name: string): AttachKind | null {
  const ext = /\.([a-z0-9]+)$/i.exec(name)?.[1];
  return ext ? (OK_TYPES[ext.toLowerCase()] ?? null) : null;
}

export interface AttachItem {
  id: string;
  file: File;
  name: string;
  size: number;
  kind: AttachKind;
  /** 画像のサムネイル用object URL（トレイから外す・送信後に破棄する）。 */
  previewUrl?: string;
}

export interface AttachError {
  name: string;
  reason: string;
}

/**
 * 形式 → 1ファイルのサイズ → 件数 → 合計 の順に判定する。弾いたファイルは理由つきで
 * `errors`に入れ、トレイ（`items`）には入れない。
 */
export function addFiles(
  current: AttachItem[],
  files: File[],
  nextId: () => string,
): { items: AttachItem[]; errors: AttachError[] } {
  const items = current.slice();
  const errors: AttachError[] = [];
  let total = items.reduce((s, x) => s + x.size, 0);
  for (const f of files) {
    const kind = attachKind(f.name);
    if (!kind) {
      errors.push({ name: f.name, reason: "対応していない形式です" });
    } else if (f.size > ATTACH_LIMITS.file) {
      errors.push({
        name: f.name,
        reason: `1ファイル10MBを超えています（${formatSize(f.size)}）`,
      });
    } else if (items.length >= ATTACH_LIMITS.count) {
      errors.push({
        name: f.name,
        reason: "一度に添付できるのは10件までです",
      });
    } else if (total + f.size > ATTACH_LIMITS.total) {
      errors.push({
        name: f.name,
        reason: `合計50MBを超えるため追加できません（残り ${formatSize(
          ATTACH_LIMITS.total - total,
        )}）`,
      });
    } else {
      total += f.size;
      items.push({
        id: nextId(),
        file: f,
        name: f.name,
        size: f.size,
        kind,
        previewUrl:
          kind === "image" && typeof URL.createObjectURL === "function"
            ? URL.createObjectURL(f)
            : undefined,
      });
    }
  }
  return { items, errors };
}

export function totalSize(items: AttachItem[]): number {
  return items.reduce((s, x) => s + x.size, 0);
}

/**
 * クリップボードから貼り付けたスクリーンショットは`image.png`等の汎用名になるため、
 * 時刻入りの名前に付け替える。
 */
export function namePastedFile(f: File, now: Date = new Date()): File {
  if (f.name && f.name !== "image.png") return f;
  const p = (n: number) => String(n).padStart(2, "0");
  return new File(
    [f],
    `スクリーンショット ${p(now.getHours())}${p(now.getMinutes())}${p(now.getSeconds())}.png`,
    { type: f.type },
  );
}

/** オーケストレータへ送る形（JSON＋base64）。 */
export interface AttachmentPayload {
  name: string;
  mimeType: string;
  dataBase64: string;
}

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result ?? "");
      resolve(url.slice(url.indexOf(",") + 1));
    };
    reader.onerror = () =>
      reject(new Error(`${file.name} を読み込めませんでした`));
    reader.readAsDataURL(file);
  });
}

/** 添付をbase64にする。1件終わるごとに`onProgress(完了件数)`を呼ぶ。 */
export async function encodeAttachments(
  items: AttachItem[],
  onProgress?: (done: number) => void,
): Promise<AttachmentPayload[]> {
  const out: AttachmentPayload[] = [];
  for (const it of items) {
    out.push({
      name: it.name,
      mimeType: it.file.type,
      dataBase64: await readAsBase64(it.file),
    });
    onProgress?.(out.length);
  }
  return out;
}

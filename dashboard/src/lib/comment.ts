import type { IssueComment, IssueDetail, IssueSummary } from "./types";

export function latestComment(issue: IssueSummary): IssueComment | undefined {
  return issue.comments[issue.comments.length - 1];
}

export interface ReplyQuoteSource {
  comment: IssueComment;
  /** trueのとき引用元はコメントではなくissue本文（コメントが0件の場合）。 */
  isIssueBody: boolean;
}

/**
 * issue一覧からの返信で引用表示する内容を決める（issue #231）。最新コメントがあればそれを、
 * コメントが0件ならissue本文をIssueComment形式に変換して返す。本文も空なら引用なし（null）。
 */
export function replyQuoteSource(detail: IssueDetail): ReplyQuoteSource | null {
  const last = detail.comments[detail.comments.length - 1];
  if (last) return { comment: last, isIssueBody: false };
  if (!stripBotMarkers(detail.body)) return null;
  return {
    comment: {
      body: detail.body,
      createdAt: detail.created_at ?? "",
      author: detail.author ?? undefined,
      url: detail.url ?? "",
    },
    isIssueBody: true,
  };
}

// オーケストレータが投稿したコメントにはBOT_COMMENT_MARKER（HTMLコメント）が
// 付与されている（orchestrator/orchestrator/github_client.py参照）。表示上は不要なので取り除く。
export function stripBotMarkers(body: string): string {
  return body.replace(/<!--[\s\S]*?-->/g, "").trim();
}

// `gh issue comment --attach`で添付されたファイルのURL（issue #218）。
const ASSET_URL =
  /^https:\/\/github\.com\/user-attachments\/assets\/[0-9a-fA-F-]{36}$/;
const FILE_URL =
  /^https:\/\/github\.com\/user-attachments\/files\/\d+\/([^/?#\s)]+)$/;
const IMAGE_LINE = /^\s*!\[([^\]]*)\]\((\S+?)(?:\s+"[^"]*")?\)\s*$/;
const VIDEO_TAG_LINE =
  /^\s*<video\b[^>]*?\bsrc="([^"]+)"[^>]*>(?:\s*<\/video>)?\s*$/i;

export type AttachmentLine =
  | { kind: "image"; alt: string; url: string }
  | { kind: "video"; url: string }
  | { kind: "file"; name: string; url: string };

/**
 * 添付ファイルだけで構成された行を判定する。画像は`![alt](url)`、動画は単独行のURLまたは
 * `<video src>`、ファイルは単独行のURL。添付ファイル以外のURLは対象外（通常の文字列扱い）。
 */
export function parseAttachmentLine(line: string): AttachmentLine | null {
  const image = line.match(IMAGE_LINE);
  if (image && ASSET_URL.test(image[2])) {
    return { kind: "image", alt: image[1], url: image[2] };
  }
  const videoTag = line.match(VIDEO_TAG_LINE);
  if (videoTag && ASSET_URL.test(videoTag[1])) {
    return { kind: "video", url: videoTag[1] };
  }
  const bare = line.trim();
  if (ASSET_URL.test(bare)) return { kind: "video", url: bare };
  const file = bare.match(FILE_URL);
  if (file)
    return { kind: "file", name: decodeURIComponent(file[1]), url: bare };
  return null;
}

/**
 * 添付ファイルのURLをオーケストレータ経由のプロキシURLに変換する。Privateリポジトリの
 * 添付ファイルはブラウザから直接取得できないため、サーバー側のトークンで取得させる。
 */
export function attachmentProxyUrl(url: string): string {
  return `/api/attachment?url=${encodeURIComponent(url)}`;
}

/** カード用の1行要約（改行・連続空白を圧縮）。添付ファイルの行は除き、末尾に件数を付ける。 */
export function commentSummary(comment: IssueComment): string {
  const kept: string[] = [];
  let images = 0;
  let videos = 0;
  let files = 0;
  for (const line of stripBotMarkers(comment.body).split("\n")) {
    const attachment = parseAttachmentLine(line);
    if (!attachment) {
      kept.push(line);
    } else if (attachment.kind === "image") {
      images++;
    } else if (attachment.kind === "video") {
      videos++;
    } else {
      files++;
    }
  }
  const counts = [
    images ? `画像${images}件` : "",
    videos ? `動画${videos}件` : "",
    files ? `ファイル${files}件` : "",
  ].filter(Boolean);
  const text = kept.join("\n").replace(/\s+/g, " ").trim();
  return counts.length ? `${text} [${counts.join("・")}]`.trim() : text;
}

export interface InlineSegment {
  text: string;
  code: boolean;
}

export type CommentBlock =
  | { kind: "heading"; text: string }
  | { kind: "paragraph"; segs: InlineSegment[] }
  | { kind: "list"; items: { mark: string; segs: InlineSegment[] }[] }
  | { kind: "code"; text: string }
  | { kind: "image"; alt: string; url: string }
  | { kind: "video"; url: string }
  | { kind: "file"; name: string; url: string };

function inlineSegments(text: string): InlineSegment[] {
  return text
    .split(/(`[^`]+`)/)
    .filter(Boolean)
    .map((part) =>
      part.length > 1 && part.startsWith("`") && part.endsWith("`")
        ? { text: part.slice(1, -1), code: true }
        : { text: part.replace(/\*\*/g, ""), code: false },
    );
}

/**
 * コメント本文を、見出し（行全体を**で囲んだ行）・段落・箇条書き・コードブロック・添付ファイル（画像・動画・ファイル）に
 * 分解する簡易Markdownパーサ（Claude Design ProducerDesk.dc.htmlの parseBlocks 相当）。
 */
export function parseCommentBlocks(body: string): CommentBlock[] {
  const blocks: CommentBlock[] = [];
  let para: string[] = [];
  let list: { mark: string; segs: InlineSegment[] }[] | null = null;
  let code: string[] | null = null;

  const flushPara = () => {
    if (para.length) {
      blocks.push({ kind: "paragraph", segs: inlineSegments(para.join("\n")) });
      para = [];
    }
  };
  const flushList = () => {
    if (list) {
      blocks.push({ kind: "list", items: list });
      list = null;
    }
  };

  for (const line of stripBotMarkers(body).split("\n")) {
    if (code) {
      if (line.trim().startsWith("```")) {
        blocks.push({ kind: "code", text: code.join("\n") });
        code = null;
      } else {
        code.push(line);
      }
      continue;
    }
    if (line.trim().startsWith("```")) {
      flushPara();
      flushList();
      code = [];
      continue;
    }
    const attachment = parseAttachmentLine(line);
    if (attachment) {
      flushPara();
      flushList();
      blocks.push(attachment);
      continue;
    }
    const item = line.match(/^\s*(?:([-*・])|(\d+)\.)\s+(.*)$/);
    if (item) {
      flushPara();
      (list ??= []).push({
        mark: item[2] ? `${item[2]}.` : "•",
        segs: inlineSegments(item[3]),
      });
      continue;
    }
    if (!line.trim()) {
      flushPara();
      flushList();
      continue;
    }
    const heading = line.match(/^\*\*(.+)\*\*$/);
    if (heading) {
      flushPara();
      flushList();
      blocks.push({ kind: "heading", text: heading[1] });
      continue;
    }
    flushList();
    para.push(line);
  }
  if (code) blocks.push({ kind: "code", text: code.join("\n") });
  flushPara();
  flushList();
  return blocks;
}

/** 「2026-10-05 12:58」形式（ローカルタイム）。 */
export function formatCommentTime(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

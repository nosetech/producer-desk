import type { IssueComment, IssueDetail, IssueSummary } from "./types";

export function latestComment(issue: IssueSummary): IssueComment | undefined {
  return issue.comments[issue.comments.length - 1];
}

export interface ReplyQuoteSource {
  /** 引用候補（古い→新しい順）。issue本文の場合は1件のみ。 */
  comments: IssueComment[];
  /** trueのとき引用元はコメントではなくissue本文（コメントが0件の場合）。 */
  isIssueBody: boolean;
}

/**
 * issue一覧からの返信で引用表示する内容を決める（issue #231, #245）。コメントがあればその全件
 * （古い→新しい順。初期表示は末尾）を、コメントが0件ならissue本文をIssueComment形式に変換した
 * 1件を返す。本文も空なら引用なし（null）。
 */
export function replyQuoteSource(detail: IssueDetail): ReplyQuoteSource | null {
  if (detail.comments.length > 0) {
    return { comments: detail.comments, isIssueBody: false };
  }
  if (!stripBotMarkers(detail.body)) return null;
  return {
    comments: [
      {
        body: detail.body,
        createdAt: detail.created_at ?? "",
        author: detail.author ?? undefined,
        url: detail.url ?? "",
      },
    ],
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

export type BodySegment = { kind: "markdown"; text: string } | AttachmentLine;

/**
 * コメント本文を、Markdownとして描画する区間と添付ファイル（画像・動画・ファイル）の行に分割する。
 * react-markdownは単独行のURLや`<video>`を扱えないため、添付行だけを先に取り出す。
 * コードブロック（```）内の行は添付として扱わない。
 */
export function splitAttachments(body: string): BodySegment[] {
  const segments: BodySegment[] = [];
  let buf: string[] = [];
  let inCode = false;

  const flush = () => {
    const text = buf.join("\n");
    if (text.trim()) segments.push({ kind: "markdown", text });
    buf = [];
  };

  for (const line of stripBotMarkers(body).split("\n")) {
    if (line.trim().startsWith("```")) inCode = !inCode;
    const attachment = inCode ? null : parseAttachmentLine(line);
    if (attachment) {
      flush();
      segments.push(attachment);
    } else {
      buf.push(line);
    }
  }
  flush();
  return segments;
}

/** 「2026-10-05 12:58」形式（ローカルタイム）。 */
export function formatCommentTime(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 判断事項セクションの見出し文言。書式仕様はdocs/basic-design.md 3-6、AIへの指示はagent_runner.pyと一致させる（issue #234）。 */
export const DECISION_POINTS_HEADING = "判断が必要な事項";

export interface DecisionPoint {
  text: string;
  /** 選択肢（入れ子の箇条書き）。無ければ空配列。 */
  options: string[];
}

function isDecisionHeading(line: string): boolean {
  const text = line
    .trim()
    .replace(/^#{1,6}\s+/, "")
    .replace(/^\*\*(.*?)\*\*$/, "$1")
    .replace(/[:：]\s*$/, "")
    .replace(/^\*\*(.*?)\*\*$/, "$1")
    .trim();
  return text === DECISION_POINTS_HEADING;
}

/**
 * コメント本文から「判断が必要な事項」セクションの番号付きリストを取り出す（issue #234）。
 * セクションが無い・リストが空・書式に従っていない場合はnull（従来の引用表示へフォールバック）。
 * コードブロック内の同名見出しは対象外。
 */
export function extractDecisionPoints(body: string): DecisionPoint[] | null {
  const lines = stripBotMarkers(body).split("\n");
  let inCode = false;
  let start = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim().startsWith("```")) {
      inCode = !inCode;
      continue;
    }
    if (!inCode && isDecisionHeading(lines[i])) {
      start = i + 1;
      break;
    }
  }
  if (start < 0) return null;

  const points: DecisionPoint[] = [];
  for (let i = start; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    const item = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (item) {
      points.push({ text: item[1].trim(), options: [] });
      continue;
    }
    const current = points[points.length - 1];
    if (!current || !/^\s+/.test(line)) break;
    const option = line.match(/^\s+[-*+]\s+(.+)$/);
    if (option) current.options.push(option[1].trim());
    else if (current.options.length)
      current.options[current.options.length - 1] += ` ${line.trim()}`;
    else current.text += ` ${line.trim()}`;
  }
  return points.length ? points : null;
}

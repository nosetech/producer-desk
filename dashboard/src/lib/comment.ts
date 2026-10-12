import type { IssueComment, IssueSummary } from "./types";

export function latestComment(issue: IssueSummary): IssueComment | undefined {
  return issue.comments[issue.comments.length - 1];
}

// オーケストレータが投稿したコメントにはBOT_COMMENT_MARKER（HTMLコメント）が
// 付与されている（orchestrator/orchestrator/github_client.py参照）。表示上は不要なので取り除く。
export function stripBotMarkers(body: string): string {
  return body.replace(/<!--[\s\S]*?-->/g, "").trim();
}

/** カード用の1行要約（改行・連続空白を圧縮）。 */
export function commentSummary(comment: IssueComment): string {
  return stripBotMarkers(comment.body).replace(/\s+/g, " ").trim();
}

export interface InlineSegment {
  text: string;
  code: boolean;
}

export type CommentBlock =
  | { kind: "heading"; text: string }
  | { kind: "paragraph"; segs: InlineSegment[] }
  | { kind: "list"; items: { mark: string; segs: InlineSegment[] }[] }
  | { kind: "code"; text: string };

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
 * コメント本文を、見出し（行全体を**で囲んだ行）・段落・箇条書き・コードブロックに
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

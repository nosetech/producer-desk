import { describe, expect, it } from "vitest";
import {
  attachmentProxyUrl,
  commentSummary,
  parseAttachmentLine,
  parseCommentBlocks,
  replyQuoteSource,
} from "./comment";
import type { IssueComment } from "./types";

const ASSET =
  "https://github.com/user-attachments/assets/07724aab-a5ec-4183-a942-845fccd103f1";
const FILE = "https://github.com/user-attachments/files/123/report%20v1.pdf";

function comment(body: string): IssueComment {
  return { body } as IssueComment;
}

describe("parseCommentBlocks（添付）", () => {
  it("画像の Markdown 記法を image ブロックにする", () => {
    expect(parseCommentBlocks(`![shot](${ASSET})`)).toEqual([
      { kind: "image", alt: "shot", url: ASSET },
    ]);
  });

  it("単独行の assets URL を video ブロックにする", () => {
    expect(parseCommentBlocks(`録画です\n\n${ASSET}`)).toEqual([
      { kind: "paragraph", segs: [{ text: "録画です", code: false }] },
      { kind: "video", url: ASSET },
    ]);
  });

  it("<video src> を video ブロックにする", () => {
    expect(
      parseCommentBlocks(`<video src="${ASSET}" controls></video>`),
    ).toEqual([{ kind: "video", url: ASSET }]);
  });

  it("files URL を file ブロックにする（名前はデコードする）", () => {
    expect(parseCommentBlocks(FILE)).toEqual([
      { kind: "file", name: "report v1.pdf", url: FILE },
    ]);
  });

  it("添付ファイル以外の画像・URL は通常の段落のまま", () => {
    const blocks = parseCommentBlocks("![x](https://example.com/a.png)");
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("paragraph");
  });

  it("コードブロック内の添付記法は展開しない", () => {
    expect(parseCommentBlocks(`\`\`\`\n![a](${ASSET})\n\`\`\``)).toEqual([
      { kind: "code", text: `![a](${ASSET})` },
    ]);
  });

  it("添付のない既存コメントのパース結果は変わらない", () => {
    expect(parseCommentBlocks("**見出し**\n- a\n- b\n\n本文")).toEqual([
      { kind: "heading", text: "見出し" },
      {
        kind: "list",
        items: [
          { mark: "•", segs: [{ text: "a", code: false }] },
          { mark: "•", segs: [{ text: "b", code: false }] },
        ],
      },
      { kind: "paragraph", segs: [{ text: "本文", code: false }] },
    ]);
  });
});

describe("parseAttachmentLine", () => {
  it("文章中の URL は対象外", () => {
    expect(parseAttachmentLine(`見てください ${ASSET}`)).toBeNull();
  });
});

describe("commentSummary", () => {
  it("添付が無ければ従来どおり1行に圧縮する", () => {
    expect(commentSummary(comment("a\n\n  b"))).toBe("a b");
  });

  it("添付の行は除き、末尾に件数を付ける", () => {
    expect(
      commentSummary(
        comment(`確認してください\n![a](${ASSET})\n${ASSET}\n${FILE}`),
      ),
    ).toBe("確認してください [画像1件・動画1件・ファイル1件]");
  });

  it("添付のみのコメントは件数だけになる", () => {
    expect(commentSummary(comment(`![a](${ASSET})`))).toBe("[画像1件]");
  });
});

describe("attachmentProxyUrl", () => {
  it("URL をエンコードしてプロキシパスに付ける", () => {
    expect(attachmentProxyUrl(ASSET)).toBe(
      `/api/attachment?url=${encodeURIComponent(ASSET)}`,
    );
  });
});

describe("replyQuoteSource", () => {
  const base = {
    repo: "o/r",
    number: 1,
    body: "issue本文",
    author: { login: "owner" },
    created_at: "2026-10-01T00:00:00Z",
    url: "https://github.com/o/r/issues/1",
  };

  it("コメントがあれば最新コメントを返す", () => {
    const comments = [comment("1件目"), comment("2件目")];
    expect(replyQuoteSource({ ...base, comments })).toEqual({
      comment: comments[1],
      isIssueBody: false,
    });
  });

  it("コメントが0件ならissue本文をIssueComment形式で返す", () => {
    expect(replyQuoteSource({ ...base, comments: [] })).toEqual({
      comment: {
        body: "issue本文",
        createdAt: "2026-10-01T00:00:00Z",
        author: { login: "owner" },
        url: "https://github.com/o/r/issues/1",
      },
      isIssueBody: true,
    });
  });

  it("コメントも本文も空ならnullを返す", () => {
    expect(replyQuoteSource({ ...base, body: " \n", comments: [] })).toBeNull();
  });
});

import { describe, expect, it } from "vitest";
import {
  attachmentProxyUrl,
  commentSummary,
  extractDecisionPoints,
  parseAttachmentLine,
  replyQuoteSource,
  splitAttachments,
} from "./comment";
import type { IssueComment } from "./types";

const ASSET =
  "https://github.com/user-attachments/assets/07724aab-a5ec-4183-a942-845fccd103f1";
const FILE = "https://github.com/user-attachments/files/123/report%20v1.pdf";

function comment(body: string): IssueComment {
  return { body } as IssueComment;
}

describe("splitAttachments", () => {
  it("画像の Markdown 記法を添付行として切り出す", () => {
    expect(splitAttachments(`![shot](${ASSET})`)).toEqual([
      { kind: "image", alt: "shot", url: ASSET },
    ]);
  });

  it("単独行の assets URL を video として切り出す", () => {
    expect(splitAttachments(`録画です\n\n${ASSET}`)).toEqual([
      { kind: "markdown", text: "録画です\n" },
      { kind: "video", url: ASSET },
    ]);
  });

  it("<video src> を video として切り出す", () => {
    expect(splitAttachments(`<video src="${ASSET}" controls></video>`)).toEqual(
      [{ kind: "video", url: ASSET }],
    );
  });

  it("files のURLを file として切り出す", () => {
    expect(splitAttachments(FILE)).toEqual([
      {
        kind: "file",
        name: "report v1.pdf",
        url: FILE,
      },
    ]);
  });

  it("添付ファイル以外の画像は Markdown 区間のまま", () => {
    const text = "![x](https://example.com/a.png)";
    expect(splitAttachments(text)).toEqual([{ kind: "markdown", text }]);
  });

  it("コードブロック内の添付記法は展開しない", () => {
    const text = `\`\`\`\n![a](${ASSET})\n\`\`\``;
    expect(splitAttachments(text)).toEqual([{ kind: "markdown", text }]);
  });

  it("BOTマーカーを除去する", () => {
    expect(splitAttachments("本文\n\n<!-- m -->")).toEqual([
      { kind: "markdown", text: "本文" },
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

  it("コメントがあれば全件を古い→新しい順で返す", () => {
    const comments = [comment("1件目"), comment("2件目"), comment("3件目")];
    expect(replyQuoteSource({ ...base, comments })).toEqual({
      comments,
      isIssueBody: false,
    });
  });

  it("コメントが1件でも配列で返す", () => {
    const comments = [comment("唯一")];
    expect(replyQuoteSource({ ...base, comments })).toEqual({
      comments,
      isIssueBody: false,
    });
  });

  it("コメントが0件ならissue本文をIssueComment形式で返す", () => {
    expect(replyQuoteSource({ ...base, comments: [] })).toEqual({
      comments: [
        {
          body: "issue本文",
          createdAt: "2026-10-01T00:00:00Z",
          author: { login: "owner" },
          url: "https://github.com/o/r/issues/1",
        },
      ],
      isIssueBody: true,
    });
  });

  it("本文がBOTマーカーのみで空ならnullを返す", () => {
    expect(
      replyQuoteSource({
        ...base,
        body: "<!-- producer-desk:bot-comment -->",
        comments: [],
      }),
    ).toBeNull();
  });

  it("コメントも本文も空ならnullを返す", () => {
    expect(replyQuoteSource({ ...base, body: " \n", comments: [] })).toBeNull();
  });
});

describe("extractDecisionPoints", () => {
  it("番号付きリストと入れ子の選択肢を取り出す", () => {
    const body = [
      "作業報告です。",
      "",
      "**判断が必要な事項**",
      "1. 〇〇をA案／B案のどちらで進めるか",
      "   - A案: 速い",
      "   - B案: 安全",
      "2. PR #163をレビューし、問題なければマージする",
      "",
      "<!-- producer-desk:bot-comment -->",
    ].join("\n");
    expect(extractDecisionPoints(body)).toEqual([
      {
        text: "〇〇をA案／B案のどちらで進めるか",
        options: ["A案: 速い", "B案: 安全"],
      },
      { text: "PR #163をレビューし、問題なければマージする", options: [] },
    ]);
  });

  it("インデントされた番号付き項目も抽出する", () => {
    const body = "**判断が必要な事項**\n  1. a\n     - A案: x\n  2. b";
    expect(extractDecisionPoints(body)).toEqual([
      { text: "a", options: ["A案: x"] },
      { text: "b", options: [] },
    ]);
  });

  it("セクションが無ければnull", () => {
    expect(extractDecisionPoints("1. これは判断事項ではない")).toBeNull();
  });

  it("リストが空ならnull", () => {
    expect(
      extractDecisionPoints("**判断が必要な事項**\n\n次の段落"),
    ).toBeNull();
  });

  it("見出しの揺れ（コロン・##）を許容する", () => {
    expect(extractDecisionPoints("## 判断が必要な事項\n1. a")?.length).toBe(1);
    expect(extractDecisionPoints("**判断が必要な事項：**\n1. a")?.length).toBe(
      1,
    );
  });

  it("コードブロック内の同名見出しは対象外", () => {
    const body = "```\n**判断が必要な事項**\n1. a\n```";
    expect(extractDecisionPoints(body)).toBeNull();
  });

  it("次の見出し・段落でセクションが終わる", () => {
    const body = "**判断が必要な事項**\n1. a\n\n**補足**\n1. 別のリスト";
    expect(extractDecisionPoints(body)).toEqual([{ text: "a", options: [] }]);
  });
});

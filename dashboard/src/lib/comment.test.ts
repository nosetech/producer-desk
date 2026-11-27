import { describe, expect, it } from "vitest";
import {
  attachmentProxyUrl,
  cardDecisions,
  commentSummary,
  extractDecisionPoints,
  extractWorkReport,
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

describe("cardDecisions", () => {
  const body = (items: string[]) =>
    ["作業報告です。", "", "**判断が必要な事項**", ...items].join("\n");

  it("判断事項セクションが無ければnull（従来の要約表示）", () => {
    expect(cardDecisions("作業報告のみです。")).toBeNull();
    expect(cardDecisions("**判断が必要な事項**\n本文のみ")).toBeNull();
  });

  it("選択肢はタグを「 / 」で並べ、全文はツールチップ用に保持する", () => {
    const r = cardDecisions(
      body([
        "1. `foo`をA案／B案のどちらで進めるか",
        "   - A案: `bar`を使う",
        "   - B案: 使わない",
      ]),
    );
    expect(r).toEqual({
      total: 1,
      more: 0,
      items: [
        {
          text: "`foo`をA案／B案のどちらで進めるか",
          optionLine: "A案 / B案",
          optionTitle: "A案: barを使う\nB案: 使わない",
        },
      ],
    });
  });

  it("タグの無い選択肢は先頭14文字で省略し、5つ目以降は「ほかN」にまとめる", () => {
    const r = cardDecisions(
      body([
        "1. どれにするか",
        "   - あいうえおかきくけこさしすせそ",
        "   - 二",
        "   - 三",
        "   - 四",
        "   - 五",
        "   - 六",
      ]),
    );
    expect(r?.items[0].optionLine).toBe(
      "あいうえおかきくけこさしす… / 二 / 三 / 四 ほか2",
    );
  });

  it("3件目以降は出さず、残り件数をmoreに入れる", () => {
    const r = cardDecisions(
      body(["1. 一つ目", "2. 二つ目", "3. 三つ目", "4. 四つ目"]),
    );
    expect(r?.total).toBe(4);
    expect(r?.items.map((i) => i.text)).toEqual(["一つ目", "二つ目"]);
    expect(r?.items[0].optionLine).toBeNull();
    expect(r?.more).toBe(2);
  });
});

describe("extractWorkReport", () => {
  const wrap = (section: string) =>
    `PR #12 を作成しました。\n\n${section}\n\n詳細は以下のとおりです。\n\n<!-- producer-desk:bot-comment -->`;

  it("CI完了・指摘すべて対応済を読み取る", () => {
    expect(
      extractWorkReport(
        wrap(
          "**作業結果**\n- CI: 完了\n- レビュー: 指摘3件（対応済3件・未対応0件）",
        ),
      ),
    ).toEqual({
      ci: "done",
      review: { status: "done", total: 3, resolved: 3, unresolved: 0 },
    });
  });

  it("未対応ありを読み取る", () => {
    expect(
      extractWorkReport(
        "**作業結果**\n- CI: 完了\n- レビュー: 指摘3件（対応済2件・未対応1件）",
      )?.review,
    ).toEqual({ status: "done", total: 3, resolved: 2, unresolved: 1 });
  });

  it("CI未設定・レビュー未実施を読み取る", () => {
    expect(
      extractWorkReport("**作業結果**\n- CI: 未設定\n- レビュー: 未実施"),
    ).toEqual({ ci: "none", review: { status: "none" } });
  });

  it("指摘0件は内訳の省略を許容する", () => {
    expect(
      extractWorkReport("**作業結果**\n- CI: 完了\n- レビュー: 指摘0件")
        ?.review,
    ).toEqual({ status: "done", total: 0, resolved: 0, unresolved: 0 });
  });

  it("全角コロン・見出し記法・半角括弧の表記ゆれを許容する", () => {
    expect(
      extractWorkReport(
        "## 作業結果：\n- CI：`完了`\n- レビュー：指摘 2件 (対応済 1件、未対応 1件)",
      ),
    ).toEqual({
      ci: "done",
      review: { status: "done", total: 2, resolved: 1, unresolved: 1 },
    });
  });

  it("CIもレビューも読めなければnull", () => {
    expect(
      extractWorkReport(
        "**作業結果**\n- CI: 失敗\n- レビュー: 指摘3件（対応済1件・未対応1件）",
      ),
    ).toBeNull();
  });

  it("読めない項目だけnullにする", () => {
    expect(
      extractWorkReport("**作業結果**\n- CI: 失敗\n- レビュー: 未実施"),
    ).toEqual({ ci: null, review: { status: "none" } });
    expect(
      extractWorkReport("**作業結果**\n- CI: 完了\n- レビュー: いくつか対応"),
    ).toEqual({ ci: "done", review: null });
  });

  it("作業結果と判断事項が併記されていても区切りで止まる", () => {
    const body =
      "**作業結果**\n- CI: 完了\n- レビュー: 未実施\n\n**判断が必要な事項**\n1. 方針を決める";
    expect(extractWorkReport(body)).toEqual({
      ci: "done",
      review: { status: "none" },
    });
    expect(extractDecisionPoints(body)).toEqual([
      { text: "方針を決める", options: [] },
    ]);
  });

  it("コードブロック内の同名見出しは対象外", () => {
    expect(
      extractWorkReport(
        "書式の例:\n```\n**作業結果**\n- CI: 完了\n```\n本文のみ",
      ),
    ).toBeNull();
  });

  it("セクション無し・書式崩れはnull", () => {
    expect(
      extractWorkReport("PRを作成しました。CIも通っています。"),
    ).toBeNull();
    expect(extractWorkReport("**作業結果**\nCIは完了しました。")).toBeNull();
  });
});

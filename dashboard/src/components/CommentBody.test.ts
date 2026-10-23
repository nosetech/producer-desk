import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import CommentBody from "./CommentBody";

const ASSET =
  "https://github.com/user-attachments/assets/0123abcd-0123-4abc-8def-0123456789ab";

function render(body: string, size: "viewer" | "quote" = "viewer") {
  return renderToStaticMarkup(createElement(CommentBody, { body, size }));
}

describe("CommentBody", () => {
  it("# 見出しをh1〜として描画する", () => {
    expect(render("# タイトル\n\n## 小見出し")).toMatch(/<h1[^>]*>タイトル/);
    expect(render("## 小見出し")).toMatch(/<h2[^>]*>小見出し/);
  });

  it("テーブルを横スクロール用のラッパー付きで描画する", () => {
    const html = render("| a | b |\n|---|---|\n| 1 | 2 |");
    expect(html).toMatch(/<div[^>]*><table/);
    expect(html).toContain("<th");
  });

  it("リンクは別タブ・noreferrerで開き、http(s)以外は描画しない", () => {
    const html = render("[x](https://example.com) [y](javascript:alert(1))");
    expect(html).toMatch(/<a [^>]*href="https:\/\/example.com"/);
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noreferrer"');
    expect(html).not.toContain("javascript:");
  });

  it("チェックボックスは無効化して表示する", () => {
    const html = render("- [x] done\n- [ ] todo");
    expect(html).toContain('type="checkbox"');
    expect(html).toContain("disabled");
  });

  it("引用・水平線・太字・斜体を描画する", () => {
    const html = render("> 引用\n\n---\n\n**太** *斜*");
    expect(html).toContain("<blockquote");
    expect(html).toContain("<hr");
    expect(html).toContain("<strong>太</strong>");
    expect(html).toContain("<em>斜</em>");
  });

  it("生HTMLは描画しない", () => {
    const html = render("<script>alert(1)</script><b>raw</b>");
    expect(html).not.toContain("<script");
    expect(html).not.toContain("<b>");
  });

  it("BOTマーカーを表示しない", () => {
    const html = render("本文\n\n<!-- producer-desk:bot-comment -->");
    expect(html).toContain("本文");
    expect(html).not.toContain("bot-comment");
  });

  it("添付画像はプロキシURL経由、外部画像は描画しない", () => {
    const html = render(
      `![shot](${ASSET})\n\n![ext](https://example.com/a.png)`,
    );
    expect(html).toContain("/api/attachment?url=");
    expect(html).not.toContain("example.com/a.png");
  });

  it("従来の**見出し**と箇条書きを崩さず描画する", () => {
    const html = render("**見出し**\n\n- a\n- b", "quote");
    expect(html).toContain("<strong>見出し</strong>");
    expect(html).toContain("<li");
  });
});

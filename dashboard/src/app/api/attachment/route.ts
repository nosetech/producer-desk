import { ORCHESTRATOR_URL } from "@/lib/orchestrator";

// issueコメントの添付画像・動画をオーケストレータ経由で配信する（issue #218）。
// Privateリポジトリの添付ファイルは、オーケストレータがサーバー側のGitHubトークンで取得する。
// 動画のシークのためRangeヘッダを中継し、本文はバッファせずストリームのまま返す。
export async function GET(request: Request) {
  const url = new URL(request.url).searchParams.get("url");
  if (!url) {
    return Response.json({ error: "urlクエリが必要です" }, { status: 400 });
  }
  const headers: Record<string, string> = {};
  const range = request.headers.get("Range");
  if (range) headers.Range = range;

  let res: globalThis.Response;
  try {
    res = await fetch(
      `${ORCHESTRATOR_URL}/api/attachment?url=${encodeURIComponent(url)}`,
      { headers, cache: "no-store" },
    );
  } catch {
    return Response.json(
      { error: `オーケストレータ（${ORCHESTRATOR_URL}）に接続できません` },
      { status: 502 },
    );
  }

  const passthrough = new Headers();
  for (const name of [
    "Content-Type",
    "Content-Length",
    "Content-Range",
    "Accept-Ranges",
    "Cache-Control",
  ]) {
    const value = res.headers.get(name);
    if (value) passthrough.set(name, value);
  }
  return new Response(res.body, { status: res.status, headers: passthrough });
}

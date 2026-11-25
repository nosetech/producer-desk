import { proxyToOrchestrator } from "@/lib/orchestrator";

// 返信欄の定型文（issue #323）。永続化・検証はオーケストレータの`/api/snippets`
// （basic-design.md 2-5）が担うため、そのままプロキシする。
export async function GET() {
  return proxyToOrchestrator("/api/snippets");
}

export async function POST(request: Request) {
  const body = await request.text();
  return proxyToOrchestrator("/api/snippets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

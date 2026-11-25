import { proxyToOrchestrator } from "@/lib/orchestrator";

// 定型文の並び替え（issue #323）。
export async function PUT(request: Request) {
  const body = await request.text();
  return proxyToOrchestrator("/api/snippets/order", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

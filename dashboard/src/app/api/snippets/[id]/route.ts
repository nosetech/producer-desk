import { proxyToOrchestrator } from "@/lib/orchestrator";

// 定型文の更新・削除（issue #323）。
export async function PUT(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const body = await request.text();
  return proxyToOrchestrator(`/api/snippets/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  return proxyToOrchestrator(`/api/snippets/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

import { proxyToOrchestrator } from "@/lib/orchestrator";

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ key: string }> },
) {
  const { key } = await params;
  const body = await request.text();
  return proxyToOrchestrator(`/api/prompts/${encodeURIComponent(key)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ key: string }> },
) {
  const { key } = await params;
  return proxyToOrchestrator(`/api/prompts/${encodeURIComponent(key)}`, {
    method: "DELETE",
  });
}

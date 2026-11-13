import { proxyToOrchestrator } from "@/lib/orchestrator";

// inbox項目の登録（issue #288）。
export async function POST(
  request: Request,
  { params }: { params: Promise<{ owner: string; name: string }> },
) {
  const { owner, name } = await params;
  const body = await request.text();
  return proxyToOrchestrator(`/api/projects/${owner}/${name}/inbox`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

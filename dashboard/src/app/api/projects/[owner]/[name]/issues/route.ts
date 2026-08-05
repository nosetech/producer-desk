import { proxyToOrchestrator } from "@/lib/orchestrator";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ owner: string; name: string }> },
) {
  const { owner, name } = await params;
  const body = await request.text();
  return proxyToOrchestrator(`/api/projects/${owner}/${name}/issues`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

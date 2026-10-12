import { proxyToOrchestrator } from "@/lib/orchestrator";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ owner: string; name: string }> },
) {
  const { owner, name } = await params;
  return proxyToOrchestrator(`/api/projects/${owner}/${name}/refresh`, {
    method: "POST",
  });
}

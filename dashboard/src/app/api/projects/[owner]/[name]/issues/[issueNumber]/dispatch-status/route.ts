import { proxyToOrchestrator } from "@/lib/orchestrator";

export async function GET(
  _request: Request,
  {
    params,
  }: { params: Promise<{ owner: string; name: string; issueNumber: string }> },
) {
  const { owner, name, issueNumber } = await params;
  return proxyToOrchestrator(
    `/api/projects/${owner}/${name}/issues/${issueNumber}/dispatch-status`,
  );
}

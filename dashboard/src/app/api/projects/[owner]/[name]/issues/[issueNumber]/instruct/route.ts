import { proxyToOrchestrator } from "@/lib/orchestrator";

export async function POST(
  request: Request,
  {
    params,
  }: { params: Promise<{ owner: string; name: string; issueNumber: string }> },
) {
  const { owner, name, issueNumber } = await params;
  const body = await request.text();
  return proxyToOrchestrator(
    `/api/projects/${owner}/${name}/issues/${issueNumber}/instruct`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    },
  );
}

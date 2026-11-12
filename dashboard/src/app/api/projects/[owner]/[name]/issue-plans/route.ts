import { proxyToOrchestrator } from "@/lib/orchestrator";

// AIによるissue計画の生成（issue #287）。issueは作成しない。
export async function POST(
  request: Request,
  { params }: { params: Promise<{ owner: string; name: string }> },
) {
  const { owner, name } = await params;
  const body = await request.text();
  return proxyToOrchestrator(`/api/projects/${owner}/${name}/issue-plans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

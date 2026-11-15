import { proxyToOrchestrator } from "@/lib/orchestrator";

type Ctx = { params: Promise<{ owner: string; name: string }> };

// AI計画ジョブの一覧（issue #299）。inbox項目とinboxIssueNumberで突き合わせる。
export async function GET(_request: Request, { params }: Ctx) {
  const { owner, name } = await params;
  return proxyToOrchestrator(`/api/projects/${owner}/${name}/issue-plans`);
}

// AI計画ジョブの投入（issue #299）。202で即時返り、完了は待たない。issueは作成しない。
export async function POST(request: Request, { params }: Ctx) {
  const { owner, name } = await params;
  const body = await request.text();
  return proxyToOrchestrator(`/api/projects/${owner}/${name}/issue-plans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

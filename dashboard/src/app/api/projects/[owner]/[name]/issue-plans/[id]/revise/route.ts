import { proxyToOrchestrator } from "@/lib/orchestrator";

// 計画ジョブのrevise（issue #299）。バックグラウンドで実行され、202で即時返る。
export async function POST(
  request: Request,
  { params }: { params: Promise<{ owner: string; name: string; id: string }> },
) {
  const { owner, name, id } = await params;
  const body = await request.text();
  return proxyToOrchestrator(
    `/api/projects/${owner}/${name}/issue-plans/${encodeURIComponent(id)}/revise`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body || "{}",
    },
  );
}

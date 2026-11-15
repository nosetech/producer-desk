import { proxyToOrchestrator } from "@/lib/orchestrator";

type Params = { params: Promise<{ owner: string; name: string }> };

// issueのマイルストーン・ラベル一括変更（issue #305）。
export async function PATCH(request: Request, { params }: Params) {
  const { owner, name } = await params;
  const body = await request.text();
  return proxyToOrchestrator(`/api/projects/${owner}/${name}/issues/meta`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

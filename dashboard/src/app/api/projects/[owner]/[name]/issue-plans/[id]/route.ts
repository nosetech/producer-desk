import { proxyToOrchestrator } from "@/lib/orchestrator";

type Ctx = { params: Promise<{ owner: string; name: string; id: string }> };

const target = (owner: string, name: string, id: string) =>
  `/api/projects/${owner}/${name}/issue-plans/${encodeURIComponent(id)}`;

// 計画ジョブの個別取得（issue #299）。
export async function GET(_request: Request, { params }: Ctx) {
  const { owner, name, id } = await params;
  return proxyToOrchestrator(target(owner, name, id));
}

// 確認画面での直接編集（タイトル・本文）の保存。
export async function PATCH(request: Request, { params }: Ctx) {
  const { owner, name, id } = await params;
  const body = await request.text();
  return proxyToOrchestrator(target(owner, name, id), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

// 破棄、または承認（issue登録）後の削除。
export async function DELETE(_request: Request, { params }: Ctx) {
  const { owner, name, id } = await params;
  return proxyToOrchestrator(target(owner, name, id), { method: "DELETE" });
}

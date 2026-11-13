import { proxyToOrchestrator } from "@/lib/orchestrator";

type Params = {
  params: Promise<{ owner: string; name: string; issueNumber: string }>;
};

// inbox項目の編集・削除（issue #288）。
export async function PATCH(request: Request, { params }: Params) {
  const { owner, name, issueNumber } = await params;
  const body = await request.text();
  return proxyToOrchestrator(
    `/api/projects/${owner}/${name}/inbox/${issueNumber}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body,
    },
  );
}

export async function DELETE(_request: Request, { params }: Params) {
  const { owner, name, issueNumber } = await params;
  return proxyToOrchestrator(
    `/api/projects/${owner}/${name}/inbox/${issueNumber}`,
    { method: "DELETE" },
  );
}

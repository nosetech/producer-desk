import { proxyToOrchestrator } from "@/lib/orchestrator";
import {
  loadLiteLlmModelsForRepo,
  loadProjectExecutionSettings,
} from "@/lib/projectsConfig";

// 現在値・選択肢の取得は`config/projects.yaml`/`config/litellm_config.yaml`を
// 直接読む（`/api/projects`と同じ方式）。永続化（更新）はオーケストレータの
// `PATCH /api/projects/{repo}/settings`（basic-design.md 4章）が担うため、
// そちらへプロキシする。
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ owner: string; name: string }> },
) {
  const { owner, name } = await params;
  const repo = `${owner}/${name}`;
  const [settings, availableModels] = await Promise.all([
    loadProjectExecutionSettings(repo),
    loadLiteLlmModelsForRepo(repo),
  ]);
  return Response.json({
    repo,
    ...settings,
    available_models: availableModels,
  });
}

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ owner: string; name: string }> },
) {
  const { owner, name } = await params;
  const body = await request.text();
  return proxyToOrchestrator(`/api/projects/${owner}/${name}/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

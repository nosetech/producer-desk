import { proxyToOrchestrator } from "@/lib/orchestrator";

// Agent Runnerプロンプト設定の一覧取得（issue #149）。永続化・検証はオーケストレータの
// `/api/prompts`（basic-design.md 3-6）が担うため、そのままプロキシする。
export async function GET() {
  return proxyToOrchestrator("/api/prompts");
}

import { proxyToOrchestrator } from "@/lib/orchestrator";

export async function GET() {
  return proxyToOrchestrator("/api/state");
}

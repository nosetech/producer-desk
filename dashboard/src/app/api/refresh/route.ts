import { proxyToOrchestrator } from "@/lib/orchestrator";

export async function POST() {
  return proxyToOrchestrator("/api/refresh", { method: "POST" });
}

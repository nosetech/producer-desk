import { proxyToOrchestrator } from "@/lib/orchestrator";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ progressId: string }> },
) {
  const { progressId } = await params;
  return proxyToOrchestrator(`/api/progress/${progressId}`);
}

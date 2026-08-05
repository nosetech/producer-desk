import "server-only";

export const ORCHESTRATOR_URL =
  process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8787";

export async function proxyToOrchestrator(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  let res: globalThis.Response;
  try {
    res = await fetch(`${ORCHESTRATOR_URL}${path}`, {
      ...init,
      cache: "no-store",
    });
  } catch {
    return Response.json(
      { error: `オーケストレータ（${ORCHESTRATOR_URL}）に接続できません` },
      { status: 502 },
    );
  }
  const body = await res.text();
  return new Response(body, {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("Content-Type") ?? "application/json",
    },
  });
}

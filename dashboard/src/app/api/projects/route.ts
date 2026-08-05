import { loadProjectRepos } from "@/lib/projectsConfig";

export async function GET() {
  const repos = await loadProjectRepos();
  return Response.json({ repos });
}

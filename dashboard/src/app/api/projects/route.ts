import { loadProjectsWithExecutionSettings } from "@/lib/projectsConfig";

export async function GET() {
  const { repos, settings } = await loadProjectsWithExecutionSettings();
  return Response.json({ repos, settings });
}

import {
  loadAllProjectExecutionSettings,
  loadProjectRepos,
} from "@/lib/projectsConfig";

export async function GET() {
  const [repos, settings] = await Promise.all([
    loadProjectRepos(),
    loadAllProjectExecutionSettings(),
  ]);
  return Response.json({ repos, settings });
}

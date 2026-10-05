import ProjectIssues from "@/components/ProjectIssues";

export default async function ProjectIssuesPage({
  params,
}: {
  params: Promise<{ owner: string; name: string }>;
}) {
  const { owner, name } = await params;
  const repo = `${decodeURIComponent(owner)}/${decodeURIComponent(name)}`;
  // プロジェクト切替時にフィルタ等の画面内状態を引き継がないよう、repoをkeyにする。
  return <ProjectIssues key={repo} repo={repo} />;
}

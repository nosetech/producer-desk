"""オーケストレータのエントリポイント（雛形）。

現時点ではプロジェクト基盤セットアップ（issue #11）の一部として、
config/projects.yaml の読み込みと起動確認のみを行う。
ポーリング・ディスパッチ本体は後続issueで実装する。
"""

from __future__ import annotations

from orchestrator.config import load_projects


def main() -> None:
    projects = load_projects()

    if not projects:
        print("config/projects.yaml にプロジェクトが登録されていません。")
        return

    print(f"{len(projects)}件のプロジェクトを読み込みました:")
    for project in projects:
        print(f"  - {project.repo} ({project.worktree_path})")


if __name__ == "__main__":
    main()

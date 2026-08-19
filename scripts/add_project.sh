#!/bin/bash
# 新規プロジェクトをproducer-deskの管理対象に追加するサポートツール。
# 以下を1コマンドで行う（docs/basic-design.md 2-1、issue #128）。
#   1. 対象リポジトリへの5つの状態ラベルの作成（冪等）
#   2. 対象リポジトリのベースcloneとAgent Runner実行用worktreeの用意（冪等）
#   3. config/projects.yaml への repo/worktree_path エントリ追記
#
# 使い方:
#   ./scripts/add_project.sh <owner/repo> <worktree-path> [base-branch]
#
#   owner/repo     対象リポジトリ（例: nosetech/project-a）
#   worktree-path  Agent Runner実行用worktreeを作成するパス（絶対パス推奨）
#   base-branch    worktreeのベースブランチ（省略時: develop。省略時のみ、対象
#                  リポジトリに存在しなければ main → master の順にフォールバック
#                  する。明示的に指定した場合はフォールバックせず、見つからなければ
#                  エラーになる）
#
# 前提: gh CLI（gh auth login済み）・git・python3（config/projects.yaml更新に使用、
# 追加パッケージのインストールは不要）
#
# 非スコープ: プロジェクトの削除・無効化、オーケストレータの自動再起動（実行完了後、
# 再起動が必要な旨を案内するのみに留める。運用中の他プロジェクトのディスパッチ
# キューを不用意に中断させないため）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECTS_CONFIG_PATH="${PROJECTS_CONFIG_PATH:-${REPO_ROOT}/config/projects.yaml}"
BASE_CLONE_ROOT="${HOME}/.producer-desk/repos"

log() {
    echo "[add_project] $*"
}

err() {
    echo "[add_project] $*" >&2
}

usage() {
    cat <<EOF
使い方: $(basename "$0") <owner/repo> <worktree-path> [base-branch]

  owner/repo     対象リポジトリ（例: nosetech/project-a）
  worktree-path  Agent Runner実行用worktreeを作成するパス
  base-branch    worktreeのベースブランチ（省略時: develop、無ければ main → master。
                 明示指定時はフォールバックせず見つからなければエラー）
EOF
}

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    usage
    exit 1
fi

TARGET_REPO="$1"
WORKTREE_PATH="$2"
REQUESTED_BASE_BRANCH="${3:-develop}"
if [ "$#" -eq 3 ]; then
    BASE_BRANCH_EXPLICIT=true
else
    BASE_BRANCH_EXPLICIT=false
fi

if ! [[ "${TARGET_REPO}" =~ ^[^/]+/[^/]+$ ]]; then
    err "owner/repo 形式で指定してください（例: nosetech/project-a）: ${TARGET_REPO}"
    exit 1
fi

for cmd in gh git python3; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        err "${cmd} が見つかりません。インストールしてください。"
        exit 1
    fi
done

# --- 1. 状態ラベルの作成（冪等） ---
# 色はproducer-desk自身に現在設定済みの値をテンプレートとして使う
# （orchestrator/orchestrator/labels.py の STATUS_LABELS と同じ5つ）。
declare -a STATUS_LABEL_NAMES=(
    "status:todo"
    "status:in-progress"
    "needs-human-decision"
    "status:in-review"
    "status:closed"
)
declare -a STATUS_LABEL_COLORS=(
    "ededed"
    "1d76db"
    "d93f0b"
    "5319e7"
    "2ea44f"
)

log "対象リポジトリ ${TARGET_REPO} の状態ラベルを確認します..."
# デフォルトの--limit（30）だとラベル数の多いリポジトリで既存ラベルを見落とし、
# 後続のgh label createが「既に存在する」エラーで失敗しうるため明示的に広げる。
existing_labels="$(gh label list --repo "${TARGET_REPO}" --limit 100 --json name -q '.[].name')"

for i in "${!STATUS_LABEL_NAMES[@]}"; do
    name="${STATUS_LABEL_NAMES[$i]}"
    color="${STATUS_LABEL_COLORS[$i]}"
    if grep -Fxq "${name}" <<<"${existing_labels}"; then
        log "ラベル '${name}' は既に存在するためスキップします"
    else
        gh label create --repo "${TARGET_REPO}" "${name}" --color "${color}"
        log "ラベル '${name}' を作成しました"
    fi
done

# --- 2. ベースcloneとworktreeの用意（冪等） ---
BASE_CLONE_PATH="${BASE_CLONE_ROOT}/${TARGET_REPO}"

if [ -d "${BASE_CLONE_PATH}/.git" ]; then
    log "ベースclone ${BASE_CLONE_PATH} は既に存在するため fetch のみ行います..."
    git -C "${BASE_CLONE_PATH}" fetch origin
else
    log "ベースclone ${BASE_CLONE_PATH} を作成します..."
    mkdir -p "$(dirname "${BASE_CLONE_PATH}")"
    gh repo clone "${TARGET_REPO}" "${BASE_CLONE_PATH}"
fi

# ベースclone自身がブランチ名を保持していると、後続の`git worktree add
# <worktree-path> <base-branch>`が同名ブランチを別worktreeで同時チェックアウト
# しようとして失敗しうる（orchestrator/orchestrator/worktree.pyと同じ制約）。
# そのためベースclone側は常にdetached HEADにしてブランチ名を空けておく。
git -C "${BASE_CLONE_PATH}" checkout --detach HEAD --quiet

resolve_base_branch() {
    local candidates=("${REQUESTED_BASE_BRANCH}")
    # 3番目の引数でベースブランチを明示指定した場合（タイプミスを含む）は、
    # 省略時デフォルト（develop）向けのフォールバックを適用せずそのままエラーにする。
    if [ "${BASE_BRANCH_EXPLICIT}" = false ]; then
        [ "${REQUESTED_BASE_BRANCH}" = "main" ] || candidates+=("main")
        [ "${REQUESTED_BASE_BRANCH}" = "master" ] || candidates+=("master")
    fi

    local candidate
    for candidate in "${candidates[@]}"; do
        if git -C "${BASE_CLONE_PATH}" ls-remote --exit-code --heads origin "${candidate}" >/dev/null 2>&1; then
            echo "${candidate}"
            return 0
        fi
    done
    return 1
}

if ! BASE_BRANCH="$(resolve_base_branch)"; then
    if [ "${BASE_BRANCH_EXPLICIT}" = true ]; then
        err "指定されたベースブランチ '${REQUESTED_BASE_BRANCH}' が見つかりません"
    else
        err "ベースブランチが見つかりません（指定: ${REQUESTED_BASE_BRANCH}、フォールバック: main, master）"
    fi
    exit 1
fi
if [ "${BASE_BRANCH}" != "${REQUESTED_BASE_BRANCH}" ]; then
    log "ブランチ '${REQUESTED_BASE_BRANCH}' が見つからないため '${BASE_BRANCH}' にフォールバックします"
fi

if [ -e "${WORKTREE_PATH}" ]; then
    # 既存パスが本当に対象リポジトリのworktreeかどうかを確認せずスキップすると、
    # 別プロジェクトと取り違えたパスをそのままconfig/projects.yamlに登録して
    # しまいうる（issue #128レビュー指摘）。originのURLに owner/repo 文字列が
    # 含まれるかどうかで簡易的に一致確認する。
    if ! git -C "${WORKTREE_PATH}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        err "worktree ${WORKTREE_PATH} は既に存在しますが、gitのworktreeではないようです。パスを確認してください。"
        exit 1
    fi
    existing_origin_url="$(git -C "${WORKTREE_PATH}" remote get-url origin 2>/dev/null || true)"
    if [[ "${existing_origin_url}" != *"${TARGET_REPO}"* ]]; then
        err "worktree ${WORKTREE_PATH} は既に存在しますが、対象リポジトリ ${TARGET_REPO} のものではないようです（origin: ${existing_origin_url:-不明}）。パスを確認してください。"
        exit 1
    fi
    log "worktree ${WORKTREE_PATH} は既に存在し、対象リポジトリと一致することを確認したため作成をスキップします"
else
    log "worktree ${WORKTREE_PATH}（ベースブランチ: ${BASE_BRANCH}）を作成します..."
    mkdir -p "$(dirname "${WORKTREE_PATH}")"
    git -C "${BASE_CLONE_PATH}" worktree add "${WORKTREE_PATH}" "${BASE_BRANCH}"
fi

# --- 3. config/projects.yaml の更新 ---
log "config/projects.yaml (${PROJECTS_CONFIG_PATH}) を更新します..."
python3 "${SCRIPT_DIR}/_add_project_entry.py" "${PROJECTS_CONFIG_PATH}" "${TARGET_REPO}" "${WORKTREE_PATH}"

log "完了しました。オーケストレータの再起動が必要です。"

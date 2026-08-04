# producer-desk

自走型AI開発オーケストレーションシステム。設計ドキュメントは [`docs/`](./docs/) を参照（[`CLAUDE.md`](./CLAUDE.md) に読む順序の案内あり）。

## 構成

```
dashboard/      ダッシュボード Web UI（Next.js）
orchestrator/   オーケストレータ（Python、GitHub Issuesポーリング・ディスパッチ）
config/         設定ファイル（projects.yaml 等。実データはコミットしない）
logs/           Agent Runner実行ログ（コミットしない）
```

## ローカル開発環境のセットアップ

### 前提

- Node.js 20以降
- Python 3.11以降
- [GitHub CLI (`gh`)](https://cli.github.com/) がインストール済みで `gh auth login` 済みであること

### 1. dashboard（Next.js）

```bash
cd dashboard
npm install
npm run dev
```

`http://localhost:3000` で起動確認できる。Tailscale経由でのアクセスに切り替える場合は、Tailscale IPを環境変数 `TAILSCALE_IP` に設定した上で `npm run dev:tailscale` / `npm run start:tailscale` を使う（[`docs/basic-design.md` 6-2](./docs/basic-design.md#6-2-ネットワークアクセスの認証設計)）。

### 2. orchestrator（Python）

```bash
cd orchestrator
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

`config/projects.yaml` を用意した上で（下記参照）、以下で起動確認できる。

```bash
python -m orchestrator.main
```

5分間隔でのGitHub Issuesポーリング・状態集約（`GET /api/state`）、指示出し内部API（`POST /api/projects/{repo}/issues/{issue_number}/instruct` 等）、Agent Runner（Claude Code CLI）へのディスパッチまでを行う（[`docs/basic-design.md`](./docs/basic-design.md) 2〜3章）。ダッシュボードUI本体は後続issueで実装する。

### 3. config/projects.yaml の作成

[`config/projects.yaml.example`](./config/projects.yaml.example) をコピーして `config/projects.yaml` を作成し、対象リポジトリとworktreeパスを記載する（[`docs/basic-design.md` 2-1](./docs/basic-design.md#2-1-対象リポジトリ一覧の管理)）。このファイルは `.gitignore` 対象であり、実データをコミットしない。

```bash
cp config/projects.yaml.example config/projects.yaml
```

### 4. Slack Webhook URL等のsecrets

Slack Incoming WebhookのURLはリポジトリにコミットせず、環境変数 `SLACK_WEBHOOK_URL` またはローカルのsecretsファイル（`.env` 等、`.gitignore` 対象）で管理する（[`docs/basic-design.md` 5-1](./docs/basic-design.md#5-1-slack設定手順)）。

## ログ出力先ディレクトリの運用方針

Agent Runner（`claude -p`）の標準出力・標準エラー出力は `logs/<repo>/<timestamp>.log` としてローカルに保存する（[`docs/basic-design.md` 3-2](./docs/basic-design.md#3-2-監視方法)）。`logs/` ディレクトリ自体はリポジトリに含めるが、中身のログファイルはコミットしない（`.gitignore` 参照）。ディレクトリが存在しない場合はオーケストレータが実行時に作成する想定。

# producer-desk

自走型AI開発オーケストレーションシステム。設計ドキュメントは [`docs/`](./docs/) を参照（[`CLAUDE.md`](./CLAUDE.md) に読む順序の案内あり）。

## 構成

```
dashboard/      ダッシュボード Web UI（Next.js）
orchestrator/   オーケストレータ（Python、GitHub Issuesポーリング・ディスパッチ）
config/         設定ファイル（projects.yaml 等。実データはコミットしない）
logs/           Agent Runner実行ログ・bin/start.shのログ/PIDファイル（コミットしない）
bin/            起動・停止スクリプト（bin/start.sh / bin/stop.sh）
scripts/        運用スクリプト（config/usage.dbの日次バックアップ等）
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

`http://localhost:3000` で起動確認できる。

**同一LAN内の別端末（スマートフォン等）からアクセスする場合**は、自機のLAN IPを環境変数 `LAN_IP` に設定した上で `npm run dev:lan` / `npm run start:lan` を使う（[`docs/basic-design.md` 6-2](./docs/basic-design.md#6-2-ネットワークアクセスの認証設計)）。LAN IPは以下で確認できる。

```bash
# macOS（Wi-Fi接続時の例。有線の場合はen0をen1等に読み替える）
ipconfig getifaddr en0

# Linux
hostname -I
```

```bash
LAN_IP=192.168.1.xx npm run dev:lan
```

同一LAN内の別端末のブラウザで `http://<LAN_IP>:3000` を開いてダッシュボードが表示されることを確認する。アプリケーションレベルの追加認証（Basic認証等）は設けていないため、信頼できるLAN内でのみ利用すること。外出先からのアクセスにはTailscale対応（別issue、`docs/requirements.md` 4-2参照）が必要になる。

なお、オーケストレータの内部API（後述）はダッシュボードのサーバーサイドから同一マシン上で呼び出す構成のため、LANに公開する必要は無く `127.0.0.1` のままでよい。

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

5分間隔でのGitHub Issuesポーリング・状態集約（`GET /api/state`）、指示出し内部API（`POST /api/projects/{repo}/issues/{issue_number}/instruct` 等）、Agent Runner（Claude Code CLI）へのディスパッチ、判断待ち新規発生時のSlack通知までを行う（[`docs/basic-design.md`](./docs/basic-design.md) 2〜3章・5章）。既定のbindポートは`8787`だが、環境変数 `ORCHESTRATOR_PORT` で上書きできる。運用インスタンス（後述「[リリース・日常運用](#リリース日常運用)」参照）を動かしたまま別インスタンスを動作確認したい場合に使う。

Agent Runnerの起動コマンドには常に `--dangerously-skip-permissions` が付与される（`orchestrator/orchestrator/agent_runner.py` の `build_claude_command`。worktreeディレクトリ内でのフル自動実行を許可し、`.claude/settings.json` 等による別途の権限モード指定は行わない。[`docs/basic-design.md` 6-1](./docs/basic-design.md#6-1-agent-runnerのサンドボックス権限設定)参照）。また、オーケストレータの内部APIにアプリケーションレベルの追加認証（Basic認証等）は実装していない（[6-2](./docs/basic-design.md#6-2-ネットワークアクセスの認証設計)参照）。

### 3. config/projects.yaml の作成

[`config/projects.yaml.example`](./config/projects.yaml.example) をコピーして `config/projects.yaml` を作成し、対象リポジトリとworktreeパスを記載する（[`docs/basic-design.md` 2-1](./docs/basic-design.md#2-1-対象リポジトリ一覧の管理)）。このファイルは `.gitignore` 対象であり、実データをコミットしない。

```bash
cp config/projects.yaml.example config/projects.yaml
```

### 4. Slack Webhook URL等のsecrets

Slack Incoming WebhookのURLはリポジトリにコミットせず、環境変数 `SLACK_WEBHOOK_URL` またはローカルのsecretsファイル（[`orchestrator/.env.example`](./orchestrator/.env.example) をコピーして作成する `orchestrator/.env` 等、`.gitignore` 対象）で管理する（[`docs/basic-design.md` 5-1](./docs/basic-design.md#5-1-slack設定手順)）。未設定の場合、オーケストレータは判断待ち発生時のSlack通知処理を単にスキップする（起動エラーにはならない）。`python -m orchestrator.main` を直接起動する開発時のフローでは`.env`は自動で読み込まれないため、`set -a; source orchestrator/.env; set +a` 等で自分でexportすること（`bin/start.sh` を使う場合は起動時に自動で読み込まれる。後述）。

## ログ出力先ディレクトリの運用方針

Agent Runner（`claude -p`）の標準出力・標準エラー出力は `logs/<repo>/<timestamp>.log` としてローカルに保存する（[`docs/basic-design.md` 3-2](./docs/basic-design.md#3-2-監視方法)）。`logs/` ディレクトリ自体はリポジトリに含めるが、中身のログファイルはコミットしない（`.gitignore` 参照）。ディレクトリが存在しない場合はオーケストレータが実行時に作成する想定。

`bin/start.sh`（後述）で起動したdashboard・orchestrator自体の標準出力・標準エラー出力は `logs/dashboard.log` / `logs/orchestrator.log` に出力される。上記のAgent Runner個別実行ログ（`logs/<repo>/`以下）とは別物なので混同しないこと。

## リリース・日常運用

開発時のように`npm run dev`・`python -m orchestrator.main`を都度手動起動するのではなく、プロデューサーが日常的に使い続けるためにバックグラウンドで起動・停止する場合は、`bin/start.sh` / `bin/stop.sh` を使う。前提として、上記「ローカル開発環境のセットアップ」の1（`dashboard/node_modules`のインストール）と3（`config/projects.yaml`の作成）を済ませておくこと（orchestrator用のPython仮想環境は`bin/start.sh`が無ければ自動作成するため、事前準備は不要）。

### 起動・停止

```bash
./bin/start.sh
```

- dashboardを `npm run build` でビルドした上で本番モード（`next start`）、orchestratorを `python -m orchestrator.main` を、それぞれバックグラウンドで起動する
- orchestrator用のPython仮想環境（`orchestrator/.venv`）が無ければ自動的に作成し、`pip install -e .`で依存関係を導入してから起動する。既に`orchestrator/.venv`または`orchestrator/venv`が存在する場合はそれをそのまま使う
- 起動したプロセスのPIDを `logs/orchestrator.pid` / `logs/dashboard.pid` に記録する（`bin/stop.sh`が参照する）
- 待受ポートは環境変数 `ORCHESTRATOR_PORT`（既定: `8787`）・`DASHBOARD_PORT`（既定: `3000`）で上書きできる。同一LAN内の別端末にdashboardを公開する場合は環境変数 `LAN_IP` を設定する（`next start --hostname "$LAN_IP"` で起動する。オーケストレータの内部APIは常に`127.0.0.1`のみで待ち受けるためLAN公開時もこちらの設定は不要。[ネットワークアクセスの認証設計](./docs/basic-design.md#6-2-ネットワークアクセスの認証設計)参照）
- これらの環境変数はシェルでのexportに加えて、`orchestrator/.env`（`ORCHESTRATOR_PORT`等、[`orchestrator/.env.example`](./orchestrator/.env.example)参照）・`dashboard/.env`（`DASHBOARD_PORT`・`LAN_IP`、[`dashboard/.env.example`](./dashboard/.env.example)参照）に設定してもよい（`bin/start.sh`が起動時に読み込む）

```bash
LAN_IP=192.168.1.xx ./bin/start.sh
```

- 既に起動中の場合は二重起動を防止してエラー終了する（先に`./bin/stop.sh`を実行すること）。PIDファイルが残っているがプロセスが存在しない場合（前回異常終了時等）は、そのPIDファイルを削除した上で起動を続行する

停止する場合:

```bash
./bin/stop.sh
```

- PIDファイルを元にそれぞれのプロセスへ`SIGTERM`を送る。10秒待っても終了しない場合は`SIGKILL`で強制終了する
- PIDファイルが無い、または記録されたプロセスが既に終了している場合はその旨を表示してエラー終了する（片方だけ起動していた場合、起動している側だけを正しく停止する）

### 運用インスタンスと開発インスタンスの同時起動

`bin/start.sh`で起動した運用インスタンスを止めずに、機能追加・修正の動作確認用インスタンスを並行起動したい場合がある。この場合、以下3点を運用インスタンスと分離する必要がある。

1. **ポート**: orchestratorは環境変数 `ORCHESTRATOR_PORT`（既定: `8787`）、dashboardは`next dev`/`next start`の`-p`オプション（既定: `3000`）でそれぞれ上書きする。開発用dashboardから開発用orchestratorを参照させる場合は、`ORCHESTRATOR_URL`環境変数も同じポートに合わせて設定する
2. **対象プロジェクトの設定ファイル**: 環境変数 `PROJECTS_CONFIG_PATH`（既定: `config/projects.yaml`）で、開発用インスタンスには運用中の実プロジェクトを含まない別ファイル（テスト用プロジェクトのみを記載したもの）を指定する
3. **セッション永続化ファイル**: 環境変数 `SESSIONS_PATH`（既定: `config/sessions.json`）で、開発用インスタンスには別ファイルを指定する

```bash
cd orchestrator
ORCHESTRATOR_PORT=8788 \
  PROJECTS_CONFIG_PATH=../config/projects.dev.yaml \
  SESSIONS_PATH=../config/sessions.dev.json \
  python -m orchestrator.main
```

```bash
cd dashboard
ORCHESTRATOR_URL=http://127.0.0.1:8788 npm run dev -- -p 3001
```

**2・3を分離せず、開発用インスタンスの対象に運用中の実プロジェクトを含めてしまうと、同一issue・同一worktreeへ運用インスタンスと開発インスタンスの双方から同時にAgent Runnerがディスパッチされうる**（[`docs/basic-design.md` 3-3](./docs/basic-design.md#3-3-オーケストレータagent-runnerのインターフェース仕様)が前提とする「1プロジェクトにつき同時に1つの`claude -p`プロセスのみ実行」が崩れ、同一worktreeへの同時書き込みが起こりうる）。開発時は`config/projects.dev.yaml`等にテスト用プロジェクトのみを記載し、運用中の実プロジェクトを対象に含めないこと。

### 補足: `NODE_ENV`について

`next build`は、呼び出し元のシェルで環境変数`NODE_ENV`に`production`/`development`/`test`以外の値が設定されていると、内部エラー（`<Html> should not be imported outside of pages/_document.`等）で失敗することがある（[vercel/next.js#77262](https://github.com/vercel/next.js/discussions/77262)参照）。`bin/start.sh`は起動前に常に`NODE_ENV=production`を設定するため通常は意識不要だが、`dashboard`ディレクトリで直接`npm run build`を実行する場合にビルドが失敗する場合は、シェルの`NODE_ENV`環境変数の値を確認すること。

## DBバックアップ（macOS launchd）

`config/usage.db`（利用量・コスト記録用SQLite、[`docs/basic-design.md` 2-2](./docs/basic-design.md#2-2-データ取得仕様ポーリング)参照）は`.gitignore`対象のローカルファイルで、GitHubから再構築できない唯一のデータのため、`scripts/backup_usage_db.sh`と`launchd`のper-user LaunchAgentを使って日次バックアップする。

### セットアップ

```bash
cp scripts/com.nosetech.producer-desk.backup-usage-db.plist.example \
  ~/Library/LaunchAgents/com.nosetech.producer-desk.backup-usage-db.plist
```

コピー後のファイル内の `/path/to/producer-desk` を、このリポジトリの実際の絶対パスに書き換える（`ProgramArguments`・`StandardOutPath`・`StandardErrorPath`の3箇所）。

```bash
launchctl load -w ~/Library/LaunchAgents/com.nosetech.producer-desk.backup-usage-db.plist
```

読み込み後は毎日3:00（JST。システムのタイムゾーン設定に従う）に自動実行される。バックアップ先はデフォルト`~/Backups/producer-desk/`で、環境変数`BACKUP_DEST_DIR`で上書きできる（`launchd`から実行する場合はplistの`EnvironmentVariables`キーで設定する）。保持世代数はデフォルト30日分で、環境変数`BACKUP_RETENTION_DAYS`で上書きできる。

即時実行して動作確認する場合:

```bash
launchctl start com.nosetech.producer-desk.backup-usage-db
```

`logs/backup_usage_db.log`に実行結果が出力され、バックアップ先ディレクトリにタイムスタンプ付きのファイル（例: `usage-20260811-030000.db`）が作成されていることを確認する。

停止する場合:

```bash
launchctl unload ~/Library/LaunchAgents/com.nosetech.producer-desk.backup-usage-db.plist
```

### 復元手順

オーケストレータを停止した状態で、復元したいバックアップファイルを`config/usage.db`に上書きコピーする。

```bash
cp ~/Backups/producer-desk/usage-<timestamp>.db config/usage.db
```

# producer-desk 開発者向けガイド

producer-deskを**利用するだけ**の場合は[README.md](./README.md)（[GitHub Releases](https://github.com/nosetech/producer-desk/releases)のtarballを使う手順）を参照してください。本書はソースコードをgit cloneしてproducer-desk自体の開発に参加する場合の手順です。

## 設計ドキュメント

`docs/`以下に設計ドキュメントがまとまっている。前段の内容を前提として積み上がっているため、以下の順に読むこと（詳細は[CLAUDE.md](./CLAUDE.md)参照）。

1. [`docs/requirements.md`](./docs/requirements.md) — 要件定義
2. [`docs/architecture.md`](./docs/architecture.md) — アーキテクチャ設計
3. [`docs/basic-design.md`](./docs/basic-design.md) — 基本設計（ラベルによる状態遷移、内部API仕様、Agent Runner起動仕様等の詳細）
4. [`docs/design-prompt-dashboard.md`](./docs/design-prompt-dashboard.md) — ダッシュボード画面設計をClaude Designへ委譲するためのプロンプト

## 構成

```
dashboard/      ダッシュボード Web UI（Next.js）
orchestrator/   オーケストレータ（Python、GitHub Issuesポーリング・ディスパッチ）
config/         設定ファイル（projects.yaml 等。実データはコミットしない）
logs/           Agent Runner実行ログ・bin/start.shのログ/PIDファイル（コミットしない）
bin/            開発環境向け起動・停止スクリプト（bin/start.sh / bin/stop.sh）
dist/           配布パッケージ（tarball）向けレイアウト。開発環境向けのbin/とは別物（docs/basic-design.md 7章参照）。
                運用スクリプト（dist/scripts/、config/usage.dbの日次バックアップ・add_project.sh等）は
                配布パッケージ同梱用と共通の実体で、git clone環境でもこちらを直接使う（二重管理を避けるため）
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
pip install -e ".[dev]"
```

`config/projects.yaml` を用意した上で（下記参照）、以下で起動確認できる。

```bash
python -m orchestrator.main
```

5分間隔でのGitHub Issuesポーリング・状態集約（`GET /api/state`）、指示出し内部API（`POST /api/projects/{repo}/issues/{issue_number}/instruct` 等）、Agent Runner（Claude Code CLI）へのディスパッチ、判断待ち新規発生時のSlack通知までを行う（[`docs/basic-design.md`](./docs/basic-design.md) 2〜3章・5章）。既定のbindポートは`8787`だが、環境変数 `ORCHESTRATOR_PORT` で上書きできる。運用インスタンス（後述「日常運用」参照）を動かしたまま別インスタンスを動作確認したい場合に使う。

Agent Runnerの起動コマンドには常に `--dangerously-skip-permissions` が付与される（`orchestrator/orchestrator/agent_runner.py` の `build_claude_command`。worktreeディレクトリ内でのフル自動実行を許可し、`.claude/settings.json` 等による別途の権限モード指定は行わない。[`docs/basic-design.md` 6-1](./docs/basic-design.md#6-1-agent-runnerのサンドボックス権限設定)参照）。また、オーケストレータの内部APIにアプリケーションレベルの追加認証（Basic認証等）は実装していない（[6-2](./docs/basic-design.md#6-2-ネットワークアクセスの認証設計)参照）。

### 3. config/projects.yaml の作成

[`config/projects.yaml.example`](./config/projects.yaml.example) をコピーして `config/projects.yaml` を作成し、対象リポジトリとworktreeパスを記載する（[`docs/basic-design.md` 2-1](./docs/basic-design.md#2-1-対象リポジトリ一覧の管理)）。このファイルは `.gitignore` 対象であり、実データをコミットしない。

```bash
cp config/projects.yaml.example config/projects.yaml
```

対象リポジトリへの状態ラベル作成・worktreeの用意・このファイルへの追記は、`dist/scripts/add_project.sh`（配布パッケージ同梱用と共通の実体。リリース時にtarball展開先ルートの`scripts/add_project.sh`として同梱される）で1コマンドにまとめて行える（`gh auth login`済みであること。冪等実装のため既にラベル・worktree・エントリが存在する場合はそれぞれスキップされる。issue #128）。このスクリプトはconfig/projects.yamlの既定パスを自身の1階層上を基準に解決するため、git clone環境でリポジトリ直下の`config/projects.yaml`を対象にする場合は`--projects-config-path`（または環境変数`PROJECTS_CONFIG_PATH`）で明示的に指定すること。ベースcloneの配置先（既定: `~/.producer-desk/repos`）を変えたい場合は`--base-clone-root`を指定する。

```bash
./dist/scripts/add_project.sh nosetech/project-a /path/to/worktree/project-a \
  --projects-config-path="$(pwd)/config/projects.yaml"
```

### 4. LiteLLM Proxyのセットアップ（任意、issue #176）

`config/projects.yaml`のいずれかのプロジェクトで`execution_mode: litellm_proxy`（[`docs/basic-design.md` 4章](./docs/basic-design.md#4-モデルルーター設定設計)）を使う場合のみ必要。既定の`claude_code`のみを使う運用では不要。

[`config/litellm_config.yaml.example`](./config/litellm_config.yaml.example) をコピーして `config/litellm_config.yaml` を作成し、`model_list`にプロジェクトごとのモデルエイリアスを定義する。

```bash
cp config/litellm_config.yaml.example config/litellm_config.yaml
```

```bash
./bin/litellm_proxy_start.sh
```

初回起動時、オーケストレータ本体とは別の専用venv（`litellm_proxy/.venv`）を自動作成し、`litellm[proxy]`と`orchestrator`パッケージ（カスタムコールバックが`usage_store.py`をインポートするため）をインストールしてから起動する（ネットワークアクセスが発生する）。既定では`http://127.0.0.1:4000`で待ち受ける（環境変数`LITELLM_PROXY_PORT`で上書き可）。停止する場合は`./bin/litellm_proxy_stop.sh`を実行する。

常時起動しておきたい場合は、[`dist/scripts/com.nosetech.producer-desk.litellm-proxy.plist.example`](./dist/scripts/com.nosetech.producer-desk.litellm-proxy.plist.example)を参考にlaunchdのLaunchAgentとして常駐化できる。

### 5. Slack Webhook URL等のsecrets

Slack Incoming WebhookのURLはリポジトリにコミットせず、環境変数 `SLACK_WEBHOOK_URL` またはローカルのsecretsファイル（[`orchestrator/.env.example`](./orchestrator/.env.example) をコピーして作成する `orchestrator/.env` 等、`.gitignore` 対象）で管理する（[`docs/basic-design.md` 5-1](./docs/basic-design.md#5-1-slack設定手順)）。未設定の場合、オーケストレータは判断待ち発生時のSlack通知処理を単にスキップする（起動エラーにはならない）。`python -m orchestrator.main` を直接起動する開発時のフローでは`.env`は自動で読み込まれないため、`set -a; source orchestrator/.env; set +a` 等で自分でexportすること（`bin/start.sh` を使う場合は起動時に自動で読み込まれる。後述）。

## ログ出力先ディレクトリの運用方針

Agent Runner（`claude -p`）の標準出力・標準エラー出力は `logs/<repo>/<timestamp>.log`（ファイル名の`<timestamp>`はJST基準）としてローカルに保存する（[`docs/basic-design.md` 3-2](./docs/basic-design.md#3-2-監視方法)）。`logs/` ディレクトリ自体はリポジトリに含めるが、中身のログファイルはコミットしない（`.gitignore` 参照）。ディレクトリが存在しない場合はオーケストレータが実行時に作成する想定。このAgent Runner個別実行ログは、書き込み中（実行中）のファイルを除き、`config/projects.yaml`の`log_retention_days`（既定7日、更新日時＝mtime基準）より古いものが実行完了のたびに自動削除される（issue #114）。

`bin/start.sh`（後述）で起動したdashboardの標準出力・標準エラー出力は `logs/dashboard.log` に出力される（Next.js本体のサーバーログで、以下の仕組みの対象外）。上記のAgent Runner個別実行ログ（`logs/<repo>/`以下）とは別物なので混同しないこと。

orchestrator自体のログは `logs/orchestrator.log` に、`logging`モジュールによる`時刻(JST) [レベル] メッセージ`形式で出力される。`TimedRotatingFileHandler`により日付単位でローテーション・`log_retention_days`世代分保持される。出力レベルは環境変数`ORCHESTRATOR_ENV`で切り替える（未設定時は`production`扱いで`INFO`以上のみ、`development`指定時は`DEBUG`以上の全レベルを出力する）。`bin/start.sh`はこの変数を明示的に設定しないため、運用時は常に`production`相当で起動する。

`bin/start.sh`は`nohup ... orchestrator.main`の標準出力・標準エラー出力を `logs/orchestrator.log` ではなく別ファイル `logs/orchestrator.stderr.log` へリダイレクトする（`configure_logging()`呼び出し前のクラッシュ・未捕捉例外のトレースバック等、`logging`モジュールを経由しない出力を取りこぼさないための最終フォールバック）。`TimedRotatingFileHandler`はローテーション時に`orchestrator.log`を`orchestrator.log.YYYY-MM-DD`へrenameした上で新規に開き直すため、シェル側が同じパスに`>>`でリダイレクトすると、rename後もシェル側のファイルディスクリプタは旧inodeへ書き込み続けてしまい、際限のない肥大化が別の場所で再発する（issue #114）。そのため意図的に別ファイルへ分離している。

## 日常運用（開発環境でのバックグラウンド起動）

開発時のように`npm run dev`・`python -m orchestrator.main`を都度手動起動するのではなく、git clone済みの開発環境をバックグラウンドで起動・停止したい場合は、`bin/start.sh` / `bin/stop.sh` を使う（配布パッケージ利用者向けの`dist/bin/start.sh`とは別物。README.md参照）。前提として、上記「ローカル開発環境のセットアップ」の3（`config/projects.yaml`の作成）を済ませておくこと（`dashboard/node_modules`は`bin/start.sh`が起動のたびに`npm ci`で`package-lock.json`と照合・是正するため事前の`npm install`は必須ではない。orchestrator用のPython仮想環境も`bin/start.sh`が無ければ自動作成するため、事前準備は不要）。

### 起動・停止

```bash
./bin/start.sh
```

- dashboardの依存関係を`npm ci`で`package-lock.json`と照合・是正した上で `npm run build` でビルドし、本番モード（`next start`）、orchestratorを `python -m orchestrator.main` を、それぞれバックグラウンドで起動する（`npm ci`は`package-lock.json`と一致しない`node_modules`があれば作り直すため、手動での`npm install`と`node_modules`のバージョン不整合を気にする必要はない。ネットワークアクセスが必要）
- orchestrator用のPython仮想環境（`orchestrator/.venv`）が無ければ自動的に作成し、`pip install -e .`で依存関係を導入してから起動する。既に`orchestrator/.venv`または`orchestrator/venv`が存在する場合はそれをそのまま使う（`pyproject.toml`との整合性は検証しない）
- 起動したプロセスのPIDを `logs/orchestrator.pid` / `logs/dashboard.pid` に記録する（`bin/stop.sh`が参照する）
- 待受ポートは環境変数 `ORCHESTRATOR_PORT`（既定: `8787`）・`DASHBOARD_PORT`（既定: `3000`）で上書きできる。同一LAN内の別端末にdashboardを公開する場合は環境変数 `LAN_IP` を設定する（`next start --hostname "$LAN_IP"` で起動する。オーケストレータの内部APIは常に`127.0.0.1`のみで待ち受けるためLAN公開時もこちらの設定は不要。[ネットワークアクセスの認証設計](./docs/basic-design.md#6-2-ネットワークアクセスの認証設計)参照）
- `ORCHESTRATOR_PORT`を変更すると、dashboardの接続先（`ORCHESTRATOR_URL`）も`bin/start.sh`が自動的に`http://127.0.0.1:${ORCHESTRATOR_PORT}`へ追従させる。dashboard/.envに`ORCHESTRATOR_URL`が明示指定されている場合はそちらが優先される
- これらの環境変数はシェルでのexportに加えて、`orchestrator/.env`（`ORCHESTRATOR_PORT`等、[`orchestrator/.env.example`](./orchestrator/.env.example)参照）・`dashboard/.env`（`DASHBOARD_PORT`・`LAN_IP`・`ORCHESTRATOR_URL`、[`dashboard/.env.example`](./dashboard/.env.example)参照）に設定してもよい（`bin/start.sh`が起動時に読み込む）

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

バックアップスクリプト（[`dist/scripts/backup_usage_db.sh`](./dist/scripts/backup_usage_db.sh)）とplistサンプル（[`dist/scripts/com.nosetech.producer-desk.backup-usage-db.plist.example`](./dist/scripts/com.nosetech.producer-desk.backup-usage-db.plist.example)）は配布パッケージ同梱用と共通の実体で、git clone環境でもこちらを直接使う（基本的な手順は[README.mdの「バックアップ・トラブルシューティング」](./README.md#バックアップトラブルシューティング)参照）。ただし以下の2点はgit clone環境固有の差分として読み替えること。

- plist内の`/path/to/producer-desk/scripts/backup_usage_db.sh`は、tarball展開先ではなくこのリポジトリのgit clone先の絶対パスを使った`/path/to/producer-desk/dist/scripts/backup_usage_db.sh`に読み替える（`StandardOutPath`・`StandardErrorPath`の`/path/to/producer-desk`部分も同様にgit clone先の絶対パスにする）
- `backup_usage_db.sh`はconfig/usage.dbの既定パスを自身の1階層上を基準に解決するため、`dist/scripts/`から実行するgit clone環境ではリポジトリルートの`config/usage.db`を対象にするよう環境変数`USAGE_DB_PATH`で明示的に指定する必要がある（plistから実行する場合は`EnvironmentVariables`キーに追加する）

## 開発ワークフロー

- ブランチ運用: `master`（安定版） → `develop`（結合） → `feature/*`（作業ブランチ、`develop`から切る）
- 変更は必ずPRで`develop`に取り込む。GitHub issueに対応する変更は、PR本文に独立した行として `Closes #<issue番号>` を記載する（issue番号の直後に区切り文字を挟まず日本語を続けると、GitHubの自動リンク解析がissue参照として認識しない。issue #82）
- PR作成時は `.github/workflows/` のCIでフォーマット・lint・テストが自動実行される（`orchestrator/**` / `dashboard/**` の変更パスに応じてジョブが分岐）。push前にローカルで以下を実行し、CI落ちを防ぐこと
  - `orchestrator/`: `ruff format .` → `ruff check .` → `pytest`（事前に `pip install -e ".[dev]"`）
  - `dashboard/`: `npm run format` → `npm run lint` → `npx tsc --noEmit`
- リリース（バージョンタグの発行・`master`へのマージ・`.github/workflows/release.yml`によるtarball生成）の詳細は[`docs/basic-design.md` 7章](./docs/basic-design.md#7-配布パッケージ化設計)を参照

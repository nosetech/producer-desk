# producer-desk

producer-deskは、プロデューサー1名が複数プロジェクト（3〜5件程度の同時進行を想定）のソフトウェア開発をAIエージェントに任せて監督するための、自走型AI開発オーケストレーションシステムです。GitHub issueに指示を書くと、[Claude Code](https://claude.com/product/claude-code) CLIによる「Agent Runner」がバックグラウンドで実装・PR作成まで自走し、人間の判断が必要な場面（設計判断・レビュー）だけダッシュボード経由で対応する運用を想定しています。

**開発ではなく利用したい場合**は、git cloneせず[GitHub Releases](https://github.com/nosetech/producer-desk/releases)から配布パッケージ（ビルド済みtarball）をダウンロードしてください。以下はその手順です。producer-desk自体の開発に参加する場合は[CONTRIBUTING.md](./CONTRIBUTING.md)を、内部設計を詳しく知りたい場合は[`docs/`](./docs/)を参照してください。

## 前提ソフトウェア

以下はOS側の前提としてあらかじめインストールしておく必要があります（配布パッケージには含まれません）。

- Node.js 20以降
- Python 3.11以降
- [GitHub CLI (`gh`)](https://cli.github.com/)（`gh auth login` 済みであること）
- [Claude Code CLI](https://claude.com/product/claude-code)（Pro/Maxプラン等のサブスクリプション認証済みであること。Anthropic APIの従量課金は使わない）
- macOS（DBバックアップのlaunchd連携を含め、動作確認はmacOSのみ）

Dockerは使いません（ネイティブ構成での動作を前提としています）。

## インストール

任意のディレクトリに配布パッケージ（tarball）を展開します。

```bash
tar xzf producer-desk-<version>.tar.gz
cd producer-desk-<version>
```

## 初期設定

### 対象プロジェクトの設定

`config/projects.yaml.example` をコピーして `config/projects.yaml` を作成し、AIに任せたい対象リポジトリと、そのリポジトリを展開するworktreeパスを記載します。

```bash
cp config/projects.yaml.example config/projects.yaml
```

```yaml
projects:
  - repo: nosetech/project-a
    worktree_path: /Users/producer/worktrees/project-a
```

対象リポジトリのworktree自体は事前に用意しておく必要があります。プロジェクトを追加・変更した場合は、このファイルを編集した上でproducer-deskを再起動してください。

### Slack通知設定（任意）

判断待ち・レビュー待ち発生時のSlack通知を使う場合は、`SLACK_WEBHOOK_URL` にIncoming WebhookのURLを設定します。未設定の場合、通知処理は単にスキップされます（起動エラーにはなりません）。

**方法A: `.env` ファイルに記載する（推奨）**

`.env.example` をコピーして `.env` を作成し、`SLACK_WEBHOOK_URL` の行のコメントを外してURLを記載します。起動のたびに自動で読み込まれるため、以後は環境変数を都度exportする必要がありません。`ORCHESTRATOR_PORT`・`DASHBOARD_PORT`・`LAN_IP`（後述）も同様にここで設定できます。

```bash
cp .env.example .env
# .env を編集し、SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz の
# 行のコメント（先頭の#）を外す
```

**方法B: シェルの環境変数として都度exportする**

```bash
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz
./bin/start.sh
```

`.env` に記載した値とシェルでexportした値の両方が存在する場合、`.env` 側の値で上書きされます。恒常的な設定は方法A、その場限りの一時的な上書きには方法Bを使う、という使い分けを推奨します。

## 起動・停止

```bash
./bin/start.sh
```

初回起動時、`orchestrator/.venv` を自動作成し、同梱の`orchestrator/dist/*.whl`をインストールしてから起動します（ネットワークアクセス不要、`pip install`のみ）。dashboardは`npm install`・ビルド不要のビルド済みNext.js standalone出力をそのまま起動します。

- orchestrator: `http://127.0.0.1:8787`（環境変数 `ORCHESTRATOR_PORT` で上書き可）
- dashboard: `http://127.0.0.1:3000`（環境変数 `DASHBOARD_PORT` で上書き可）

同一LAN内の別端末（スマートフォン等）からdashboardにアクセスする場合は、自機のLAN IPを環境変数 `LAN_IP` に設定してから起動します。

```bash
LAN_IP=192.168.1.xx ./bin/start.sh
```

アプリケーションレベルの追加認証（Basic認証等）は設けていないため、信頼できるLAN内でのみ利用してください（外出先からのアクセスへの対応は将来拡張、下記「システムの動作仕様」参照）。

停止する場合:

```bash
./bin/stop.sh
```

## 使い方

起動後、ブラウザで`http://127.0.0.1:3000`（またはLAN IP経由）を開くとダッシュボードが表示されます。

- **判断待ち一覧**: `needs-human-decision`ラベルが付いたissue（Agent Runnerが自ら「人間の判断が必要」と判断して停止したもの）が横断的に並びます。各カードから「承認」（定型文「承認します。進めてください。」をissueにコメント投稿し、Agent Runnerを再開させる）、または自由記述での指示（方針変更・追加情報の提供等をそのままコメント投稿する）ができます。専用の「却下」操作はなく、方針を変えたい場合も自由記述で伝えます。
- **レビュー待ち一覧**: `status:in-review`ラベルが付いたissue（Agent RunnerがPRを作成し終えたもの）が並びます。紐づくPRへのリンクが表示されるので内容を確認し、「承認」でそのPRをsquash mergeしてissueをクローズします。差し戻したい場合は自由記述で修正指示を送ると、Agent Runnerが同じPRブランチで対応を続けます。
- **新規タスクの作成**: プロジェクトを選び、タイトルと自由記述のプロンプト（指示内容）を入力してissueを新規作成できます。「即時着手」を選ぶとすぐにAgent Runnerがディスパッチされ、「todo登録」を選ぶと`status:todo`のまま登録だけ行われ、後で着手を指示できます。
- **プロジェクトの並行状況**: プロジェクト（リポジトリ）ごとに、直近更新issueの状態と状態別のissue件数が表示されます。ラベルは付いているのに対応するAgent Runnerのプロセスが実際には動いていない異常（`status:in-progress`のまま停止している等）は警告アイコンで示されます。
- **Slack通知**: 判断待ち・レビュー待ちが新規に発生すると、設定したSlackチャンネルに通知が届きます（起動時点で既に判断待ち・レビュー待ちだったissueは再通知しません）。

GitHub issueに直接コメントを書いても（ダッシュボードを介さなくても）、次回ポーリング（最大5分後）でAgent Runnerへの指示として検知されます。

## システムの動作仕様（概要）

producer-deskは独自のデータベースを持たず、**GitHub Issuesを正のデータストア**として動作します。詳細設計は[`docs/basic-design.md`](./docs/basic-design.md)を参照してください。ここでは運用者が押さえておくべき挙動の要点のみをまとめます。

- **状態はラベルで管理される**: 各issueには常に1つだけ状態ラベルが付与されます。`status:todo`（未着手）→ `status:in-progress`（作業中）→ `needs-human-decision`（判断待ち）または`status:in-review`（レビュー待ち）→ `status:closed`（完了）という流れで遷移し、いずれのラベル付け替えもAgent Runnerまたはオーケストレータ自身が自動で行います（人間が手動でラベルを付け替える必要は基本的にありません）。
- **5分間隔のポーリング**: オーケストレータは5分ごとに対象リポジトリのissue一覧を取得し、ラベル遷移の検知・判断待ち/レビュー待ちの集約・Slack通知を行います。ダッシュボードから操作した直後は同期的に最新状態へ更新されるため、5分待たずに反映されます。
- **Agent Runnerが自動で行うこと**: ディスパッチされると、Claude Code CLI（`claude -p --dangerously-skip-permissions`）が対象プロジェクトのworktree内でフル自動実行され、調査・実装・テスト・PR作成・ラベルの自己更新までを行います。1プロジェクトにつき同時に実行されるAgent Runnerは1つのみで、複数の指示が重なった場合はプロジェクトごとのキューで順次処理されます。
- **Agent Runnerが自動で行わないこと**: 設計判断が必要と自ら判断した場合は`needs-human-decision`で停止し、人間の承認なしにPRをマージすることはありません。issueのクローズ・再オープン自体（GitHub上の状態）もproducer-deskの操作範囲外で、人間またはPRマージ経由の自動クローズに委ねます。
- **権限・ネットワーク**: MVPでは同一LAN内からのアクセスのみを想定し、アプリケーションレベルの追加認証（Basic認証等）は設けていません。外出先からのアクセス（Tailscale経由）は将来拡張として別issueで対応予定です。Agent Runner自体は`--dangerously-skip-permissions`でworktree内のフル自動実行を許可されています。

## バックアップ・トラブルシューティング

### DBバックアップ（macOS launchd）

`config/usage.db`（利用量・コスト記録用SQLite）はローカルファイルで自動的にはバックアップされません。`scripts/backup_usage_db.sh` と launchd の per-user LaunchAgent を使って日次バックアップする場合は、以下の手順を行います。

```bash
cp scripts/com.nosetech.producer-desk.backup-usage-db.plist.example \
  ~/Library/LaunchAgents/com.nosetech.producer-desk.backup-usage-db.plist
```

コピー後のファイル内の `/path/to/producer-desk` を、展開先の実際の絶対パスに書き換えます（`ProgramArguments`・`StandardOutPath`・`StandardErrorPath`の3箇所）。

```bash
launchctl load -w ~/Library/LaunchAgents/com.nosetech.producer-desk.backup-usage-db.plist
```

読み込み後は毎日3:00（システムのタイムゾーン設定に従う）に自動実行されます。バックアップ先はデフォルト`~/Backups/producer-desk/`で、環境変数`BACKUP_DEST_DIR`で上書きできます（`launchd`から実行する場合はplistの`EnvironmentVariables`キーで設定します）。保持世代数はデフォルト30日分で、環境変数`BACKUP_RETENTION_DAYS`で上書きできます。

即時実行して動作確認する場合:

```bash
launchctl start com.nosetech.producer-desk.backup-usage-db
```

`logs/backup_usage_db.log`に実行結果が出力され、バックアップ先ディレクトリにタイムスタンプ付きのファイル（例: `usage-20260811-030000.db`）が作成されていることを確認します。

停止する場合:

```bash
launchctl unload ~/Library/LaunchAgents/com.nosetech.producer-desk.backup-usage-db.plist
```

復元する場合は、オーケストレータを停止した状態で、復元したいバックアップファイルを`config/usage.db`に上書きコピーします。

```bash
cp ~/Backups/producer-desk/usage-<timestamp>.db config/usage.db
```

### トラブルシューティング

- **`config/projects.yaml が見つかりません`**: 「初期設定」を実施していません。`config/projects.yaml.example` からコピーして作成してください。
- **`orchestrator/dist/*.whl が見つかりません`**: 配布パッケージ（tarball）が壊れている可能性があります。ダウンロードし直してください。
- **ポートが衝突する**: 環境変数 `ORCHESTRATOR_PORT` / `DASHBOARD_PORT` で別ポートを指定してください。
- **`orchestrator/.venv/bin/orchestrator` コマンドを直接実行しても `config/projects.yaml` が見つからないと言われる**: このコマンドは実行時のカレントディレクトリを展開先ルート（このファイルがある場所）とみなして`config/`・`logs/`を探します。必ず展開先ルートで `./bin/start.sh` 経由で起動し、`orchestrator`コマンドを別ディレクトリから直接実行しないでください。

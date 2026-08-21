# producer-desk セットアップ手順

このtarballには、producer-deskをビルド済みの状態で動かすために必要なファイル一式が含まれています。開発者向けの詳細（ソースコード・テスト・設計ドキュメント等）は含まれていません。開発に参加する場合は [GitHubリポジトリ](https://github.com/nosetech/producer-desk) を参照してください。

## 前提

以下はOS側の前提としてあらかじめインストールしておく必要があります（このtarballには含まれません）。

- Node.js 20以降
- Python 3.11以降
- [GitHub CLI (`gh`)](https://cli.github.com/)（`gh auth login` 済みであること）
- [Claude Code CLI](https://claude.com/product/claude-code)（Pro/Maxプラン等のサブスクリプション認証済みであること）
- macOS（DBバックアップのlaunchd連携を含め、動作確認はmacOSのみ）

## 1. 展開

任意のディレクトリにtarballを展開する。

```bash
tar xzf producer-desk-<version>.tar.gz
cd producer-desk-<version>
```

## 2. 対象プロジェクトの設定

`config/projects.yaml.example` をコピーして `config/projects.yaml` を作成し、対象リポジトリとworktreeパスを記載する。

```bash
cp config/projects.yaml.example config/projects.yaml
```

対象リポジトリへの状態ラベル作成・worktreeの用意・このファイルへの追記は、`scripts/add_project.sh`で1コマンドにまとめて行える（`gh auth login`済みであること）。

```bash
./scripts/add_project.sh nosetech/project-a /Users/producer/worktrees/project-a
```

ベースブランチは省略時`develop`で、対象リポジトリに無ければ`main`→`master`の順にフォールバックする（3番目の引数で明示指定も可）。既にラベル・worktree・エントリが存在する場合はそれぞれスキップされ、何度実行しても安全。実行後はこのSETUPの手順4に従ってproducer-deskを（再）起動すること。

## 3. Slack通知設定（任意）

判断待ち・レビュー待ち発生時のSlack通知を使う場合は、`SLACK_WEBHOOK_URL` にIncoming WebhookのURLを設定してから `bin/start.sh` を実行する。未設定の場合、通知処理は単にスキップされる（起動エラーにはならない）。以下いずれかの方法で設定する。

**方法A: `.env` ファイルに記載する（推奨）**

`.env.example` をコピーして `.env` を作成し、`SLACK_WEBHOOK_URL` の行のコメントを外してURLを記載する。`bin/start.sh` が起動のたびに自動で読み込むため、以後は環境変数を都度exportする必要がない。`ORCHESTRATOR_PORT`・`DASHBOARD_PORT`・`LAN_IP`（後述）も同様にここで設定できる。

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

`.env` に記載した値とシェルでexportした値の両方が存在する場合、`.env` 側の値で上書きされる（`bin/start.sh`は起動のたびに`.env`を`source`するため）。恒常的な設定は方法A、その場限りの一時的な上書きには方法Bを使う、という使い分けを推奨する。

## 4. 起動・停止

```bash
./bin/start.sh
```

初回起動時、`orchestrator/.venv` を自動作成し、同梱の `orchestrator/dist/*.whl` をインストールしてから起動する（ネットワークアクセス不要、`pip install`のみ）。dashboardは`npm install`・ビルド不要のビルド済みNext.js standalone出力をそのまま起動する。

- orchestrator: `http://127.0.0.1:8787`（環境変数 `ORCHESTRATOR_PORT` で上書き可。dashboardの接続先もこのポートに自動追従する）
- dashboard: `http://127.0.0.1:3000`（環境変数 `DASHBOARD_PORT` で上書き可）

同一LAN内の別端末（スマートフォン等）からdashboardにアクセスする場合は、自機のLAN IPを環境変数 `LAN_IP` に設定してから起動する。

```bash
LAN_IP=192.168.1.xx ./bin/start.sh
```

アプリケーションレベルの追加認証（Basic認証等）は設けていないため、信頼できるLAN内でのみ利用すること。

停止する場合:

```bash
./bin/stop.sh
```

## 5. 使い方

起動後、ブラウザで`http://127.0.0.1:3000`（またはLAN IP経由）を開くとダッシュボードが表示される。

- **判断待ち一覧**: `needs-human-decision`ラベルが付いたissue（Agent Runnerが自ら「人間の判断が必要」と判断して停止したもの）が横断的に並ぶ。各カードから「承認」（定型文「承認します。進めてください。」をissueにコメント投稿し、Agent Runnerを再開させる）、または自由記述での指示（方針変更・追加情報の提供等をそのままコメント投稿する）ができる。専用の「却下」操作はなく、方針を変えたい場合も自由記述で伝える。
- **レビュー待ち一覧**: `status:in-review`ラベルが付いたissue（Agent RunnerがPRを作成し終えたもの）が並ぶ。紐づくPRへのリンクが表示されるので内容を確認し、「承認」でそのPRをsquash mergeしてissueをクローズする。差し戻したい場合は自由記述で修正指示を送ると、Agent Runnerが同じPRブランチで対応を続ける。
- **新規タスクの作成**: プロジェクトを選び、タイトルと自由記述のプロンプト（指示内容）を入力してissueを新規作成できる。「即時着手」を選ぶとすぐにAgent Runnerがディスパッチされ、「todo登録」を選ぶと`status:todo`のまま登録だけ行われ、後で着手を指示できる。
- **プロジェクトの並行状況**: プロジェクト（リポジトリ）ごとに、直近更新issueの状態と状態別のissue件数が表示される。ラベルは付いているのに対応するAgent Runnerのプロセスが実際には動いていない異常（`status:in-progress`のまま停止している等）は警告アイコンで示される。
- **Slack通知**: 判断待ち・レビュー待ちが新規に発生すると、設定したSlackチャンネルに通知が届く（起動時点で既に判断待ち・レビュー待ちだったissueは再通知しない）。

GitHub issueに直接コメントを書いても（ダッシュボードを介さなくても）、次回ポーリング（最大5分後）でAgent Runnerへの指示として検知される。

## 6. ログ

各種ログはすべて展開先ルート直下の`logs/`ディレクトリに出力される。

- **Agent Runnerの実行ログ**: `logs/<repo>/<timestamp>.log`（`<repo>`は対象リポジトリ名、`<timestamp>`は日本時間基準の実行開始時刻）に、issueへのディスパッチ1回ごとに1ファイルとして記録される。実行中も随時追記されるため、`tail -f logs/<repo>/<timestamp>.log`で進行状況をリアルタイムに確認できる。ダッシュボードの「プロジェクトの並行状況」で異常（実行中プロセスが見つからない等）が疑われる場合の一次切り分けにも使える。古いログファイルは、`config/projects.yaml`の`log_retention_days`（既定7日）より更新日時が古くなった時点で、次回の実行完了時に自動削除される。
- **dashboardのログ**: `logs/dashboard.log`にNext.jsサーバー自体の標準出力・標準エラー出力が記録される。
- **orchestratorのログ**: `logs/orchestrator.log`に`時刻(JST) [レベル] メッセージ`形式で記録される。日付単位でローテーションし、`log_retention_days`（既定7日）分保持される。万一この仕組み自体が動き出す前にクラッシュした場合の記録は、フォールバックとして`logs/orchestrator.stderr.log`に残る。

## 7. システムの動作仕様（概要）

producer-deskは独自のデータベースを持たず、**GitHub Issuesを正のデータストア**として動作する。詳細設計は[`docs/basic-design.md`](https://github.com/nosetech/producer-desk/blob/master/docs/basic-design.md)（GitHubリポジトリ側、このtarballには同梱されない）を参照。ここでは運用者が押さえておくべき挙動の要点のみをまとめる。

- **状態はラベルで管理される**: 各issueには常に1つだけ状態ラベルが付与される。`status:todo`（未着手）→ `status:in-progress`（作業中）→ `needs-human-decision`（判断待ち）または`status:in-review`（レビュー待ち）→ `status:closed`（完了）という流れで遷移し、いずれのラベル付け替えもAgent Runnerまたはオーケストレータ自身が自動で行う（人間が手動でラベルを付け替える必要は基本的にない）。
- **5分間隔のポーリング**: オーケストレータは5分ごとに対象リポジトリのissue一覧を取得し、ラベル遷移の検知・判断待ち/レビュー待ちの集約・Slack通知を行う。ダッシュボードから操作した直後は同期的に最新状態へ更新されるため、5分待たずに反映される。
- **Agent Runnerが自動で行うこと**: ディスパッチされると、Claude Code CLI（`claude -p --dangerously-skip-permissions`）が対象プロジェクトのworktree内でフル自動実行され、調査・実装・テスト・PR作成・ラベルの自己更新までを行う。1プロジェクトにつき同時に実行されるAgent Runnerは1つのみで、複数の指示が重なった場合はプロジェクトごとのキューで順次処理される。
- **Agent Runnerが自動で行わないこと**: 設計判断が必要と自ら判断した場合は`needs-human-decision`で停止し、人間の承認なしにPRをマージすることはない。issueの再オープンはproducer-deskの操作範囲外で、再着手させたい場合は人間がGitHub上でreopenする必要がある。issueのクローズ自体は、レビュー承認時にproducer-desk（オーケストレータ）がPRのsquash merge後に明示的に行う（GitHubのPRマージによる自動クローズには依存しない。本プロジェクトのPRは`develop`向けのため、GitHubの`Closes #`による自動クローズが働かないための対処）。
- **権限・ネットワーク**: 現時点では同一LAN内からのアクセスのみを想定し、アプリケーションレベルの追加認証（Basic認証等）は設けていない。外出先からのアクセス（Tailscale経由）は将来拡張として別issueで対応予定。Agent Runner自体は`--dangerously-skip-permissions`でworktree内のフル自動実行を許可されている。

## 8. DBバックアップ（macOS launchd、任意）

`config/usage.db`（利用量・コスト記録用SQLite）はローカルファイルで自動的にはバックアップされない。`scripts/backup_usage_db.sh` と launchd の per-user LaunchAgent を使って日次バックアップする場合は、以下の手順を行う。

```bash
cp scripts/com.nosetech.producer-desk.backup-usage-db.plist.example \
  ~/Library/LaunchAgents/com.nosetech.producer-desk.backup-usage-db.plist
```

コピー後のファイル内の `/path/to/producer-desk` を、展開先の実際の絶対パスに書き換える（`ProgramArguments`・`StandardOutPath`・`StandardErrorPath`の3箇所）。

```bash
launchctl load -w ~/Library/LaunchAgents/com.nosetech.producer-desk.backup-usage-db.plist
```

読み込み後は毎日3:00（システムのタイムゾーン設定に従う）に自動実行される。バックアップ先はデフォルト`~/Backups/producer-desk/`で、環境変数`BACKUP_DEST_DIR`で上書きできる（`launchd`から実行する場合はplistの`EnvironmentVariables`キーで設定する）。保持世代数はデフォルト30日分で、環境変数`BACKUP_RETENTION_DAYS`で上書きできる。

## トラブルシューティング

- **`config/projects.yaml が見つかりません`**: 手順2を実施していない。`config/projects.yaml.example` からコピーして作成する。
- **`orchestrator/dist/*.whl が見つかりません`**: 配布パッケージ（tarball）が壊れている可能性がある。ダウンロードし直す。
- **ポートが衝突する**: 環境変数 `ORCHESTRATOR_PORT` / `DASHBOARD_PORT` で別ポートを指定する。
- **`orchestrator/.venv/bin/orchestrator` コマンドを直接実行しても `config/projects.yaml` が見つからないと言われる**: このコマンドは実行時のカレントディレクトリを展開先ルート（このファイルがある場所）とみなして`config/`・`logs/`を探す。必ず展開先ルートで `./bin/start.sh` 経由で起動し、`orchestrator`コマンドを別ディレクトリから直接実行しないこと。

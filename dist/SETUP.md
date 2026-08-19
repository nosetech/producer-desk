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

## 3. Slack通知設定（任意）

判断待ち・レビュー待ち発生時のSlack通知を使う場合は、環境変数 `SLACK_WEBHOOK_URL` にIncoming WebhookのURLを設定してから `bin/start.sh` を実行する。未設定の場合、通知処理は単にスキップされる（起動エラーにはならない）。

```bash
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz
```

## 4. 起動・停止

```bash
./bin/start.sh
```

初回起動時、`orchestrator/.venv` を自動作成し、同梱の `orchestrator/dist/*.whl` をインストールしてから起動する（ネットワークアクセス不要、`pip install`のみ）。dashboardは`npm install`・ビルド不要のビルド済みNext.js standalone出力をそのまま起動する。

- orchestrator: `http://127.0.0.1:8787`（環境変数 `ORCHESTRATOR_PORT` で上書き可）
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

## 5. DBバックアップ（macOS launchd、任意）

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

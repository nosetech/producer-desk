# 基本設計書: 自走型AI開発オーケストレーションシステム（producer-desk）

- 対応issue: [#4](https://github.com/nosetech/producer-desk/issues/4)（親issue: [#1](https://github.com/nosetech/producer-desk/issues/1)、前提issue: [#2](https://github.com/nosetech/producer-desk/issues/2) [#3](https://github.com/nosetech/producer-desk/issues/3)）
- 作成日: 2026-08-03
- 前提: [要件定義書](./requirements.md) / [アーキテクチャ設計書](./architecture.md)
- 画面設計: 本書ではワイヤーフレーム等の視覚的な設計は扱わない。Claude Designへの委譲プロンプトを[design-prompt-dashboard.md](./design-prompt-dashboard.md)としてまとめている。

## 1. データモデル・状態遷移設計

### 状態一覧・遷移条件・ラベル操作

| 状態 | ラベル | 付与するアクター | タイミング |
|---|---|---|---|
| 未着手 | `status:todo` | 人間 または AI（issue作成時） | issue作成時 |
| 作業中 | `status:in-progress` | Agent Runner（自己付与） | ディスパッチされ着手した時 |
| 判断待ち | `needs-human-decision` | Agent Runner（自己付与） | 人間の判断が必要と自ら判断した時 |
| レビュー待ち | `status:in-review` | Agent Runner（自己付与） | PRを作成した時 |
| 完了 | （ラベルなし） | 人間 | issueをクローズした時 |

状態ラベルは常に1つのみ付与される（[アーキテクチャ設計書 3章](./architecture.md#3-タスク状態管理)）。

### 冪等な状態遷移フロー

ラベルの付け替えは以下の擬似コードの通り、**現在のラベル一覧を取得してから差分のみ適用**する（PoCで判明した `--remove-label`/`--add-label` の非atomic性への対処、[poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md) 1章）。

```python
def transition_label(repo, issue_number, new_label):
    current_labels = gh_api_get_labels(repo, issue_number)
    status_labels = {"status:todo", "status:in-progress", "needs-human-decision", "status:in-review"}

    # 既に目的のラベルが付いていれば何もしない（再実行しても安全）
    if new_label in current_labels:
        return

    # 現在付与されている状態ラベルのみを個別に外す
    for label in current_labels & status_labels:
        gh_api_remove_label(repo, issue_number, label)

    gh_api_add_label(repo, issue_number, new_label)
```

- リトライ時も「現在の状態を見て必要な差分だけ適用する」ため、途中で失敗しても再実行で収束する。

### 自由記述指示によるラベル遷移ルール

ダッシュボードのテキストボックスからの自由記述指示（[2-3](#2-3-指示出しapi内部api)）は、既存issueの状態を問わず送信できる。ラベル遷移は現在の状態によって以下のように分岐する。

| 送信時の現在ラベル | ラベル遷移 | ディスパッチ |
|---|---|---|
| `status:todo` | → `status:in-progress` | 実行中でなければ即時、実行中ならキュー |
| `needs-human-decision` | → `status:in-progress` | 同上 |
| `status:in-progress` | 変更なし（割り込み指示として扱う） | 実行中のためキューに追加 |
| `status:in-review` | 変更なし | 実行中でなければ即時、実行中ならキュー |

## 2. オーケストレータ／ダッシュボードAPI設計

### 2-1. 対象リポジトリ一覧の管理

設定ファイル（`config/projects.yaml`）で管理する。

```yaml
projects:
  - repo: nosetech/project-a
    worktree_path: /Users/producer/worktrees/project-a
  - repo: nosetech/project-b
    worktree_path: /Users/producer/worktrees/project-b
```

Agent Runnerのセッション（`--session-id`/`--resume`）はプロジェクトではなくissue単位で管理するため、このファイルには含まれない（`config/sessions.json`。[3-1](#3-1-起動パラメータ)参照）。

- プロジェクト追加時は、このファイルにエントリを追加し、対象リポジトリのworktreeを用意した上でオーケストレータを再起動する（[要件定義書 2-4](./requirements.md#2-4-agent-runnerの起動停止プロジェクト追加時の運用フロー)の「手動起動・停止」＝このファイルへの登録とオーケストレータの認識、と読み替える）。

### 2-2. データ取得仕様（ポーリング）

- **ポーリング間隔**: 5分。
- 各対象リポジトリに対し `gh issue list --repo <repo> --state open --json number,title,labels,comments,updatedAt` 相当のAPI呼び出しで、Open issue一覧とラベル・コメント・更新日時を取得する。
- 取得結果から、ダッシュボード表示用に以下を集約する。
  - 判断待ち一覧: `needs-human-decision` ラベル付きissueを横断集約
  - 活動ログ（タイムライン）: 各issueの `updatedAt` とラベル遷移をイベントとして時系列に並べる
  - 利用量・リミットモニター: Claude Codeの利用量／リミット到達状況（[要件定義書 3-4](./requirements.md#3-4-コスト制約)参照）。ローカルのClaude Code使用量ログ・リミット到達検知の具体的な取得方法は実装フェーズで設計する
- **ダッシュボードへのデータ提供方式**: オーケストレータが最小限のHTTPサーバー（`http.server.ThreadingHTTPServer`、デフォルト `http://127.0.0.1:8787`）で `GET /api/state` を提供する。ポーリングスレッドが集約するたびに最新状態を更新し、リクエスト時点の最新値を `{"decisions": [...], "activity": [...]}` 形式のJSONで返す。[2-3](#2-3-指示出しapi内部api)の指示出し（POST）も同じサーバーに追加する想定

### 2-3. 指示出しAPI（内部API）

ダッシュボード（Next.js）とオーケストレータ間の内部APIは以下の通り。既存issueへの指示（承認・却下・自由記述）と、新規タスク（新規issue）の作成の2系統を持つ。

#### 既存issueへの指示

```
POST /api/projects/{repo}/issues/{issue_number}/instruct
Content-Type: application/json

{
  "action": "approve" | "reject" | "instruct",
  "message": "string（省略時はaction種別に応じた定型文を使用）"
}
```

- `approve`: 定型文「承認します。進めてください。」をissueにコメント投稿する。想定対象は `needs-human-decision` のissue。
- `reject`: 定型文（またはユーザー入力の理由）をコメント投稿し、ラベルは `needs-human-decision` のまま維持する（差し戻し。Agent Runnerの再開はプロデューサーが改めて `approve`/`instruct` するまで行わない）。定型文は「却下します。」とする。
- `instruct`: ダッシュボードのテキストボックスから入力した**自由記述のメッセージ**をコメント投稿する。issueの状態を問わず送信可能（作業中issueへの割り込み指示を含む）。
- `approve`/`instruct` はいずれも、[1章「自由記述指示によるラベル遷移ルール」](#自由記述指示によるラベル遷移ルール)に従ってラベルを更新した上で、[3章](#3-agent-runner連携設計)のAgent Runnerディスパッチを行う（対象プロジェクトが実行中でなければ即時、実行中ならプロジェクト単位のキューに追加し実行完了後に処理）。
- `reject` はコメント投稿のみでディスパッチを行わない。

#### 新規タスク（新規issue）の作成

```
POST /api/projects/{repo}/issues
Content-Type: application/json

{
  "title": "string",
  "prompt": "string",
  "dispatch": "immediate" | "queued"
}
```

- `gh issue create` 相当のAPIでissueを作成し、`status:todo` ラベルを付与する。issue本文には `prompt` をそのまま格納する。
- `dispatch: "immediate"`: 作成直後に上記「既存issueへの指示」の `instruct` と同じ扱いで即時ディスパッチ（またはプロジェクトが実行中ならキュー）する。
- `dispatch: "queued"`: `status:todo` のまま登録するだけでディスパッチしない。後日、ダッシュボードから当該issueに `instruct` を送ることで着手させる。

#### 共通仕様

- 認証は[6-2](#6-2-ネットワークアクセスの認証設計)の通りアプリレベルの追加認証は行わず、ネットワーク境界（MVPでは同一LAN内アクセスであること）に委ねる。
- 内部的な処理は `gh api repos/{repo}/issues/{issue_number}/comments` へのPOST（または新規issueの場合は `gh api repos/{repo}/issues`）として実装する（[アーキテクチャ設計書 4章](./architecture.md#4-ダッシュボードオーケストレーション)の案A）。
- 直接GitHub issue上にコメントされた指示（ダッシュボード経由でない指示）は、次回ポーリング（最大5分後）でオーケストレータが検知し、同様にディスパッチする。検知は「オーケストレータ起動後に増えたコメント」のみを対象とし、起動時点で既に付いていたコメントは既知として扱う（再起動のたびに過去のコメント履歴を再処理しないため）。

#### プロジェクト単位のディスパッチキュー

- オーケストレータはプロジェクトごとに実行中フラグ（ロック）を持つ。
- `instruct`（`approve`含む）または `dispatch: "immediate"` の新規issue作成のリクエストが届いた際、対象プロジェクトが実行中でなければ[3章](#3-agent-runner連携設計)のディスパッチを即座に行う。
- 実行中であれば、そのメッセージ（issue番号・コメント本文）をプロジェクトごとのFIFOキューに追加する。実行中の `claude -p` プロセスが終了次第、キューの先頭のメッセージで次のディスパッチを `--resume` 付きで行う。複数メッセージが溜まっている場合は1つずつ順に処理する。

### 2-4. ダッシュボードの画面設計

視覚的な画面設計（レイアウト、ワイヤーフレーム、スタイル）は本書では扱わず、Claude Designへの指示プロンプトとして[design-prompt-dashboard.md](./design-prompt-dashboard.md)にまとめている。表示すべきデータ項目・操作は[2-2](#2-2-データ取得仕様ポーリング)・[2-3](#2-3-指示出しapi内部api)の仕様に準拠する。

## 3. Agent Runner連携設計

### 3-1. 起動パラメータ

```bash
claude -p "<指示内容>" \
  --output-format json \
  --dangerously-skip-permissions \
  --chrome \
  --append-system-prompt "<ラベル自己管理指示>" \
  (--session-id <new-uuid> | --resume <session-id>)
```

- worktreeディレクトリの指定はCLIフラグではなく、Pythonの `subprocess.run(..., cwd=<worktree-path>)` で行う（実際の `claude` CLIに `--cwd` フラグは存在しないため。`--add-dir` は追加の許可ディレクトリ指定であり用途が異なる）。
- `<session-id>` は `config/sessions.json`（`.gitignore`対象、コミットしない）に**issueごと**に保存する（`"{repo}#{issue_number}": "<session-id>"`、`orchestrator/orchestrator/session_store.py`）。初回ディスパッチ時はオーケストレータが `uuid.uuid4()` を生成し `--session-id` で明示的に指定してセッションを新規作成する。生成したIDを `config/sessions.json` に書き込み、同一issueへの以降の指示では `--resume <session-id>` で再開する。
  - **プロジェクト単位ではなくissue単位である理由**: 当初はプロジェクト（リポジトリ）単位で1つのセッションIDのみを`config/projects.yaml`に保存していたが、この場合同一プロジェクト内の全issueが1本のClaude Code会話を共有してしまう。あるissueが`needs-human-decision`で停止している間に別issueが同じセッションで進行・完了すると、後から前者issueを`--resume`で再開した際、セッションの直近の会話文脈（別issueの完了報告）を引きずってしまい、再開したissue本来の内容に取り組まれない不具合が発生した（issue #32）。issueごとに独立したセッションを持つことで、他issueの進行状況に文脈が左右されないようにする。
- `--output-format json` により、実行結果（`result` フィールド等）を構造化データとして取得し、3-2のissueコメント要約に利用する。
- `--append-system-prompt` により、[1章](#1-データモデル状態遷移設計)でAgent Runner自身の責務とした`needs-human-decision`・`status:in-review`へのラベル自己付与（対象issue番号・リポジトリ名・具体的な`gh issue edit`コマンドを含む）を、指示内容の文面によらず毎回明示する（`agent_runner.py`の`AGENT_RUNNER_LABEL_INSTRUCTION`）。当初この指示が無く、PR作成後もラベルが`status:in-progress`のまま遷移しない事例が発生したため導入した（issue #33）。
- 同様に`--append-system-prompt`で、ダッシュボードのUI実装時はCLAUDE.md記載のClaude DesignのURL（`https://claude.ai/design/...`）をブラウザ操作ツール（`mcp__claude-in-chrome__*`）で開き、配色・アイコン等の視覚的詳細を確認してから実装するよう毎回明示する（`agent_runner.py`の`AGENT_RUNNER_DESIGN_VERIFICATION_INSTRUCTION`）。デザインURLは認証必須で`WebFetch`では取得できず（403）、テキストの設計文書にも色・アイコンの指定は無いため、ブラウザ操作ツールで直接見る以外に実装が細部までデザインへ追随する手段がないことが判明したため導入した（issue #33）。
- `--chrome` フラグにより、Claude in Chrome連携を明示的に有効化する。`claude -p`（非対話モード）はこの連携がデフォルト無効で、フラグなしでは`mcp__claude-in-chrome__*`ツール自体が存在せず、上記のブラウザ確認指示が機能しない（issue #33の追加原因調査で判明）。
  - **運用上の前提**: この指示が機能するには、Agent Runnerを実行するホスト上でChromeが起動しており、`claude-in-chrome`拡張がペアリング済みで、`claude.ai`にログイン済みである必要がある（就寝中などプロデューサーが操作しない時間帯にAgent Runnerが動く想定のため、事前にログイン状態を維持しておくこと）。ブラウザ操作ツールが利用できない場合、Agent Runnerはその旨を実行結果コメントに明記し、`needs-human-decision`として人間の確認を仰ぐ。

### 3-2. 監視方法

- **ヘルスチェック**: ワンショット実行のため常時稼働の監視は不要。プロセスの終了コード（0=正常終了、非0=異常終了）を確認する。異常終了時はissueに終了コード・ログパスを記載したコメントを投稿し、`needs-human-decision` ラベルに遷移させて人間の確認を促す（正常終了時のラベル遷移は、Agent Runner自身が実行中に `gh` コマンドで行う自己付与であり、オーケストレータ側では行わない。[1章](#1-データモデル状態遷移設計)参照）。
- **ログ収集**: 標準出力・標準エラー出力を `logs/<repo>/<timestamp>.log` としてローカルに保存する。加えて、正常終了時は`--output-format json`の`result`フィールドを要約としてissueコメントに投稿し、ダッシュボードの活動ログと連動させる。

### 3-3. オーケストレータ⇔Agent Runnerのインターフェース仕様

- オーケストレータはPythonの `subprocess` でClaude Code CLIを直接起動し、標準出力・終了コードを同期的に取得する（HTTP等の別プロセス間APIは設けない）。
- 1プロジェクトにつき同時に1つの `claude -p` プロセスのみ実行する（同一worktreeへの同時書き込みを避けるため、ディスパッチ中は当該プロジェクトの新規ディスパッチをキューイングする。キューの詳細は[2-3「プロジェクト単位のディスパッチキュー」](#プロジェクト単位のディスパッチキュー)参照）。

## 4. モデルルーター設定設計

[アーキテクチャ設計書 5章](./architecture.md#5-モデルルーティング)の通り、MVPではLiteLLM Proxyを導入せず、Claude Code CLIを直接利用する。そのため本書では設定ファイル構成・モデル選択ポリシーの詳細設計は行わない。将来ローカルLLMを併用する際に、LiteLLM Proxyの設定ファイル構成・論理モデル名の命名規則・使い分けポリシーの実装仕様を別途設計する。

## 5. 通知・承認フロー詳細設計

### 5-1. Slack設定手順

1. Slackワークスペースで通知用チャンネルを作成し、Incoming Webhookアプリを追加してWebhook URLを発行する。
2. Webhook URLはオーケストレータの設定（環境変数 `SLACK_WEBHOOK_URL` またはローカルのsecretsファイル）に保存する。リポジトリにはコミットしない。

### 5-2. メッセージフォーマット

判断待ち（`needs-human-decision`）が新規発生した際、以下の内容でWebhook POSTする。

```json
{
  "text": ":bell: 判断待ちが発生しました\n*リポジトリ*: nosetech/project-a\n*issue*: #12 ログイン機能のAPI設計について\nhttps://github.com/nosetech/project-a/issues/12"
}
```

レビュー待ち（`status:in-review`）が新規発生した際も、同様に以下の内容でWebhook POSTする（issue #38で、Agent Runnerがレビュー待ちにした際に通知が来ない旨の報告を受けて追加。`orchestrator/orchestrator/slack_notifier.py`の`ReviewNotifier`）。

```json
{
  "text": ":mag: レビュー待ちになりました\n*リポジトリ*: nosetech/project-a\n*issue*: #38 ブラウザエラーの調査・対応\nhttps://github.com/nosetech/project-a/issues/38"
}
```

起動時点で既に`needs-human-decision`・`status:in-review`のissueは「既知」として扱い通知しない（[2-3「共通仕様」](#2-3-指示出しapi内部api)のコメント検知と同様、オーケストレータ再起動のたびに既存の判断待ち・レビュー待ちを再通知しないための方針）。以降のポーリングで新規に判断待ち・レビュー待ちになったissueのみを、それぞれ独立に（`DecisionNotifier`・`ReviewNotifier`として）通知する。`SLACK_WEBHOOK_URL`が未設定の場合は通知処理をスキップする（起動失敗にはしない）。

### 5-3. ダッシュボードからの指示出し操作の内部処理フロー

**承認・却下・自由記述（既存issueへの指示）**

1. プロデューサーがダッシュボードで対象issueの「承認」「却下」ボタン、または自由記述の指示入力欄からメッセージを送信する。
2. ダッシュボードが[2-3](#2-3-指示出しapi内部api)の内部API（`action: "approve" | "reject" | "instruct"`）にリクエストを送信する。
3. オーケストレータが対象issueの現在のラベルを取得する（[1章](#1-データモデル状態遷移設計)の冪等フロー）。
4. `gh api` 経由でissueに定型コメント（承認・却下）または自由記述メッセージ（instruct）を投稿する。
5. `approve`/`instruct` の場合、[1章「自由記述指示によるラベル遷移ルール」](#自由記述指示によるラベル遷移ルール)に従いラベルを更新し、対象プロジェクトが実行中でなければ[3章](#3-agent-runner連携設計)のAgent Runnerディスパッチを即時実行、実行中なら[2-3「プロジェクト単位のディスパッチキュー」](#プロジェクト単位のディスパッチキュー)に追加する。`reject` の場合はラベルを維持し、ディスパッチは行わない。
6. 処理結果をダッシュボードのレスポンスとして返し、UIの判断待ち一覧・活動ログを更新する。

**新規タスク（新規issue）の作成**

1. プロデューサーがダッシュボードでプロジェクトを選択し、タイトルと自由記述のプロンプトを入力、即時着手／todo登録を選んで送信する。
2. ダッシュボードが[2-3](#2-3-指示出しapi内部api)の新規issue作成APIにリクエストを送信する。
3. オーケストレータが `gh api` 経由でissueを作成し、`status:todo` ラベルを付与する。
4. `dispatch: "immediate"` の場合、対象プロジェクトが実行中でなければ即時ディスパッチ、実行中ならキューに追加する（ラベルは `status:in-progress` に更新）。`dispatch: "queued"` の場合はここで終了する。
5. 処理結果をダッシュボードのレスポンスとして返し、UIの活動ログに新規タスク作成イベントを追加する。

## 6. 権限・セキュリティ設計

### 6-1. Agent Runnerのサンドボックス・権限設定

- `claude -p` 起動時に `--dangerously-skip-permissions` フラグを付与し、worktreeディレクトリ内でのフル自動実行を許可する（[アーキテクチャ設計書 7章](./architecture.md#7-権限管理安全対策)）。
- 設定ファイル（`.claude/settings.json`）による権限モード指定は行わず、起動コマンドを見れば挙動が一目瞭然になるようにする。

### 6-2. ネットワークアクセスの認証設計

- アプリケーションレベルの追加認証（Basic認証等）は設けない。
- **MVPでは同一LAN内からのアクセスのみ**を前提とする。ダッシュボード（Next.js）の待受プロセスは、0.0.0.0ではなく**LANインターフェースのIPにのみbind**する（`next dev`/`next start` の `--hostname <lan-ip>` オプション。`npm run dev:lan`/`npm run start:lan`、環境変数 `LAN_IP` に自機のLAN IPを設定して使う）。これにより、同一LANの外からは到達不能にする。
- オーケストレータの内部API（`GET /api/state` 等）は、ダッシュボードのRoute Handlerが**同一マシン上でサーバーサイドから**呼び出す構成（[2-2](#2-2-データ取得仕様ポーリング)参照。ブラウザから直接呼び出すことはない）のため、ネットワークインターフェースに公開する必要が無い。オーケストレータの待受プロセスは`127.0.0.1`（ループバック）にのみbindしたままとする。
- **将来拡張**: 外出先からのアクセスに対応する際は、ダッシュボードのbind先をTailscaleインターフェースIPに切り替える（`--hostname <tailscale-ip>`、`npm run dev:tailscale`/`npm run start:tailscale`）。別issue（#29）で対応する（[要件定義書 4-2](./requirements.md#4-2-将来拡張とする範囲)参照）。

## 成果物

- 本書（データモデル定義、状態遷移フロー、API仕様、Agent Runner連携仕様、通知フロー、権限設計）
- [design-prompt-dashboard.md](./design-prompt-dashboard.md)（Claude Designへの画面設計委譲プロンプト）

## 参考

- [要件定義書](./requirements.md)
- [アーキテクチャ設計書](./architecture.md)
- [poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md)

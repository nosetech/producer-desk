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
| 完了 | `status:closed` | オーケストレータ（自己付与） | issueがクローズされたことをポーリングで検知した時 |

状態ラベルは常に1つのみ付与される（[アーキテクチャ設計書 3章](./architecture.md#3-タスク状態管理)）。

issueのクローズ操作自体（人間による手動クローズ、PRマージに伴う`Closes #<issue番号>`経由の自動クローズいずれも）はproducer-deskの外側で起きるため、`status:closed`はAgent Runnerではなくオーケストレータが付与する。次回ポーリング（[2-2](#2-2-データ取得仕様ポーリング)）で対象issueがクローズ済みであることを検知し、[「冪等な状態遷移フロー」](#冪等な状態遷移フロー)と同じ`transition_label`で他の状態ラベルを`status:closed`に置き換える。

#### 管理対象外issueの扱い

`status:todo` / `status:in-progress` / `needs-human-decision` / `status:in-review` / `status:closed` のいずれも付与されていないissueは、producer-deskの管理対象外として扱う（このシステムが起票していない素のissue、まだ`status:todo`すら付いていない起票直後のissue等）。管理対象外issueは判断待ち一覧・プロジェクト状況のいずれにも表示しない（[2-2](#2-2-データ取得仕様ポーリング)参照。ただし「プロジェクトの並行状況」ウィジェットの状態別件数には`untagged`として計上される。ラベル付け漏れの検知用途、issue #115）。オーケストレータは管理対象外issueに対して`status:closed`を含むいかなる状態ラベルも自動付与しない（管理対象外issueがクローズされても何もしない。対象はあくまで4つの状態ラベルのいずれかが付与済み＝一度でもproducer-deskが着手したissueのみ）。

過去、この管理対象外という区分が無かったため、「状態ラベルが1つも付いていない」ことを一律「完了」と誤表示していた不具合があった（[issue #45](https://github.com/nosetech/producer-desk/issues/45)）。

### 冪等な状態遷移フロー

ラベルの付け替えは以下の擬似コードの通り、**現在のラベル一覧を取得してから差分のみ適用**する（PoCで判明した `--remove-label`/`--add-label` の非atomic性への対処、[poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md) 1章）。

```python
def transition_label(repo, issue_number, new_label):
    current_labels = gh_api_get_labels(repo, issue_number)
    status_labels = {
        "status:todo", "status:in-progress", "needs-human-decision",
        "status:in-review", "status:closed",
    }

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
| `status:in-review` | → `status:in-progress`（差し戻し・追加指示として扱う） | 実行中でなければ即時、実行中ならキュー |
| `status:closed` | → `status:in-progress`（再着手扱い） | 実行中でなければ即時、実行中ならキュー |

- `status:closed` のissueへの自由記述指示はラベルこそ `status:in-progress` に戻すが、GitHub issue自体のクローズ状態（Open/Closed）は変更しない（issueのクローズ・再オープンはproducer-deskの操作範囲外。[アーキテクチャ設計書](./architecture.md)参照）。再着手させたい場合は、プロデューサーが別途GitHub上でissueをreopenする運用とする。
- `status:in-review` のissueへの自由記述指示（返信）は `status:in-progress` へ即時遷移させる。当初はラベルを変更しない設計だったが、その場合ダッシュボードのレビュー待ち一覧（判定はラベルのみを見る）から返信後もカードが消えず、Agent Runnerが追加対応に着手した後でも「承認」ボタンを押せてしまい、対応中のPRをそのままマージしてしまう不具合があった（issue #95）。承認操作と同様、返信操作でも即座にラベルを更新してカードを一覧から外すことで、この競合を防ぐ。

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

- プロジェクト追加時は、このファイルにエントリを追加し、対象リポジトリのworktreeを用意した上でオーケストレータを再起動する（[要件定義書 2-4](./requirements.md#2-4-agent-runnerの起動停止プロジェクト追加時の運用フロー)の「手動起動・停止」＝このファイルへの登録とオーケストレータの認識、と読み替える）。この一連の作業（対象リポジトリへの5つの状態ラベル作成・ベースcloneとworktreeの用意・このファイルへの追記）は`dist/scripts/add_project.sh <owner/repo> <worktree-path> [base-branch] [--projects-config-path=<path>] [--base-clone-root=<path>]`で1コマンドにまとめて行える（issue #128）。`--projects-config-path`・`--base-clone-root`はいずれも省略可能で、省略時は本節既定の`config/projects.yaml`・`~/.producer-desk/repos`が使われる（`--projects-config-path`未指定時は従来通り環境変数`PROJECTS_CONFIG_PATH`もフォールバック先として使える）。このファイルはリリース時にtarball展開先ルートの`scripts/add_project.sh`として同梱される。`bin/start.sh`等（開発用ソースビルドとtarball配布用ビルド済み資産とで実際に処理内容が異なるため`bin/`・`dist/bin/`双方に別内容を持つ）とは異なり、add_project.shは開発環境・配布パッケージのどちらで動かしても処理内容が同一のため、二重管理を避けて`dist/scripts/`配下にのみ配置する。ラベル作成は`gh label create`が未作成のラベルに対する`gh issue edit --add-label`の失敗要因になりやすく見落としやすいため、特にこのツールでの一括対応を推奨する。冪等に実装されているため、既にラベル・worktree・エントリが存在する場合はそれぞれスキップされ、何度実行しても安全。オーケストレータの自動再起動は行わないため、実行完了後は案内に従って手動で再起動すること。詳細は`dist/scripts/add_project.sh`冒頭のコメントを参照。
- トップレベルの`log_retention_days`（プロジェクト単位ではなくファイル全体に1つ、既定値7）で、`logs/orchestrator.log`のローテーション世代数・`logs/<repo>/*.log`（Agent Runner個別実行ログ）の保持日数の両方を制御する（[3-2](#3-2-監視方法)参照。issue #114）。

### 2-2. データ取得仕様（ポーリング）

- **ポーリング間隔**: 5分。
- 各対象リポジトリに対し `gh issue list --repo <repo> --state all --json number,title,labels,comments,updatedAt,state --limit 100` 相当のAPI呼び出しで、issue一覧（Open・Closed双方）とラベル・コメント・更新日時・クローズ状態を取得する。
  - クローズ済みissueを「プロジェクトの並行状況」ウィジェットの状態表示に「完了」として反映するには、クローズ済みissueも取得対象に含める必要がある（[1章「完了」](#状態一覧遷移条件ラベル操作)参照）。`--state open` のみの取得では、issueがクローズされた瞬間に取得結果から消えてしまい、クローズをイベントとして検知できない（[issue #45](https://github.com/nosetech/producer-desk/issues/45)で判明）。
  - `--limit 100` はプロデューサー1名・3〜5プロジェクト同時進行というMVPの利用規模を踏まえた簡易的な上限であり、厳密なページングは行わない（1リポジトリあたり直近100件のissueに含まれない古いクローズ済みissueはプロジェクト状況の直近状態算出に現れなくなるが、実用上問題にならない想定。プロジェクト規模が想定を超えて増えた場合は別途見直す）。
- 取得結果から、以下の処理を行う。
  - **クローズ検知によるラベル遷移**: 取得したissueのうち、`state` が `CLOSED` かつ現在 `status:todo` / `status:in-progress` / `needs-human-decision` / `status:in-review` のいずれかが付与されている（＝producer-deskが管理していた）issueは、[1章「冪等な状態遷移フロー」](#冪等な状態遷移フロー)と同じ`transition_label`で `status:closed` に遷移させる。管理対象外issue（[1章「管理対象外issueの扱い」](#管理対象外issueの扱い)）はクローズされても何もしない。
  - **判断待ち一覧**: `needs-human-decision` ラベル付きissueを横断集約
  - **プロジェクト状況（並行状況ウィジェット）**: プロジェクト（リポジトリ）ごとに、直近更新issueの状態ラベルと状態別のOPEN issue件数（`status:todo` / `status:in-progress` / `needs-human-decision` / `status:in-review` の4ラベルと`untagged`の5種、`status:closed`は含まない）を集計する（`orchestrator/orchestrator/aggregation.py`の`ProjectStatus`、issue #115）。全プロジェクト横断の合計値も`AggregatedState.status_counts`として別途保持する。管理対象外issue（5つの状態ラベルいずれも無し）は直近更新状態の算出対象からは除外するが、状態別件数には`untagged`として計上する（ラベル付け漏れの検知用途。付与ラベルが無い＝完了、という誤った表示をしていた旧・活動ログ（タイムライン）の不具合[issue #45](https://github.com/nosetech/producer-desk/issues/45)の教訓を踏襲）。かつてはこの情報を全プロジェクト横断の時系列「活動ログ（タイムライン）」として提供していたが、issue #121で当該UI（`ActivityEvent`・`ActivityTimeline.tsx`）ごと廃止し、プロジェクト単位の集計（`ProjectStatus`／ダッシュボードの`ProjectStatusRow`）に一本化した。
  - **孤立したin-progress検知**: `status:in-progress` ラベルが付与されたissueは、本来[2-3「プロジェクト単位のディスパッチキュー」](#プロジェクト単位のディスパッチキュー)（`DispatchQueue`）上で実行中または待機中のはずである。しかし`gh issue edit --add-label status:in-progress`等でラベルのみを直接付与した場合（コメント投稿を伴わない操作）、`DispatchQueue.enqueue()`が一度も呼ばれずAgent Runnerが実際には起動しないまま、ダッシュボード上は「着手した」ように見え続ける不整合が発生し得ることが確認された（実例: `nosetech/stock-is#103`、[issue #50](https://github.com/nosetech/producer-desk/issues/50)）。この不整合は運用者側から`ps`やworktreeの更新時刻を手動確認する以外に検知する手段が無かった。そのため`DispatchQueue`に`is_active(repo, issue_number)`（指定issueが現在実行中または待機中かどうかを返す）を追加し、`orchestrator/orchestrator/polling.py`の`poll_once`/`run_polling_loop`から`orchestrator/orchestrator/aggregation.py`の`aggregate()`へ`is_dispatch_active`として注入する。`aggregate()`は`status:in-progress`のissueについて`is_dispatch_active(repo, number)`が偽の場合、そのプロジェクトの直近更新issueがそれであれば`ProjectStatus.is_orphaned`に異常フラグを立てる。`is_dispatch_active`を渡さない呼び出し（判定不能な文脈）では常に`False`（異常なし）を返し誤検知を避ける。
    - **ダッシュボード表示**: 当初はタイムライン項目のドット色を警告色（`--warn`/`--warn-bg`、ダーク`#ff6a5b`・ライト`#d23a2c`）に切り替え、項目直下に▲アイコン＋「実行中プロセスが見つかりません」の警告ボックスを表示する実装だった（`ActivityTimeline.tsx`、issue #50）。issue #121でのタイムライン廃止に伴い、この警告表示は`ProjectStatusRow`のチップ側（プロジェクトの並行状況ウィジェット）に移設した。`is_orphaned`が真のプロジェクトは、チップ内のリポジトリ名の隣に▲警告アイコン（`--accent-red`、タイトル属性に「作業中ラベルですが、対応するAgent Runnerが実行されていません」の説明文）を表示するのみの最小限のインジケータとし、詳細（どのissueが孤立in-progress状態か）はプロジェクト単位のissue一覧を表示する専用ページ（issue #116、未実装）に譲る方針とした。旧実装にあった「正常時（実行中）」の補足表示（`--accent-blue`系ボックス）は、チップの粒度では対応する項目が無いため廃止した。既存の`--accent-red`/`--accent-red-bg`トークンを使用（ダーク値はClaude Designの`--warn`と完全一致、ライト値はデザインの`#d23a2c`に対し既存トークンが`#d9392a`とわずかに異なるが、視覚的な差異はほぼ無いため既存トークンをそのまま流用した）。
  - **同一ポーリングサイクル内のラベル遷移の即時反映**: `poll_once`が`on_issues_fetched`（`comment_watcher.py`の`process_new_comments`・`close_watcher.py`の`close_finished_issues`、いずれもGitHub issueへの直接コメント経由の指示検知・issueクローズ検知）を呼び出す際、これらの内部で`transition_label`によりGitHub側のラベルが書き換わることがある。この変更は`on_issues_fetched`呼び出し前に取得済みの`issues_by_repo`スナップショットには反映されないため、そのまま`aggregate()`に渡すと同一サイクルのプロジェクト状況に遷移前の古いラベルとして反映され、次回ポーリング（最大5分後）まで意図した新しい状態が表示されない不具合があった（issue #97）。そのため`poll_once`は`on_issues_fetched`呼び出し後に`issues_by_repo`を`list_issues`で再取得し直し（`status:in-review`のPR番号解決も再実行）、`aggregate()`にはこの最新スナップショットを渡す。これによりポーリング1サイクルあたりのGitHub API呼び出し回数が増える（issue一覧取得が最大2回）が、ダッシュボードの操作反映と同水準の即時性を得るためのトレードオフとして許容する。`on_issues_fetched`を渡さない呼び出し（`server._refresh_store`等、オーケストレータ自身によるラベル遷移が起きない経路）ではこの再取得は行わない。なお、ユーザーがGitHub UI/`gh`コマンドで直接ラベルを編集した場合は、オーケストレータがその変更を能動的に把握できないため、従来通り次回ポーリングでの検知に委ねる（[issue #50](https://github.com/nosetech/producer-desk/issues/50)の設計と同様）。
  - **利用量・リミットモニター**（[要件定義書 3-4](./requirements.md#3-4-コスト制約)参照）: Agent Runnerの実行結果（`claude -p ... --output-format stream-json --verbose`のNDJSON出力から取り出した最後の`"type":"result"`イベント。[3-1](#3-1-起動パラメータ)参照）から`total_cost_usd`・`usage.*`・`modelUsage.*`（モデルごとのinput/outputトークン数・コスト）を取得し、`orchestrator/orchestrator/usage_store.py`でSQLite（`config/usage.db`、.gitignore対象）に記録する。Anthropicアカウント側が内部管理するセッション5時間枠・週間上限に対する正確な消費率(%)はこの経路では取得できないため、過去7日分の「日単位・モデル別の使用量」を集計して表示する方式に転換した（issue #60）。リミット到達時（`is_error: true`かつ`api_error_status: 429`）は、`result`の自由文から解除予定時刻の記述を正規表現で抽出し、パース失敗時は生の文字列をそのまま保持するフォールバックを用意した。集計結果とリミット到達状況は内部API `GET /api/usage`（[2-2](#2-2-データ取得仕様ポーリング)直下、`/api/state`と同じサーバー）で提供する。issue #59（タスク種別に応じたローカルLLM併用）を見据え、記録スキーマは`model`をモデル名の文字列として保持しており、ローカルLLM分の実データもそのまま同じ経路で記録できる。ダッシュボード側のUI（折れ線グラフ等の表示）実装は別issue（#64）に切り出した。**「日単位」の集計はJST（Asia/Tokyo）基準の日付で行う。** `usage_records.recorded_at`自体はUTCで保存するが（絶対時刻として一意に扱うため変更しない）、`daily_model_usage()`の「本日」判定・日付グルーピングはJSTへ変換してから行う。ダッシュボード側の「本日の使用量」カードが表示する日付も、集計結果の末尾要素に依存せずクライアント側でJST基準の実日付を独立に算出する（`todayJst()`、`Intl.DateTimeFormat`の`Asia/Tokyo`タイムゾーン指定を使用）。UTC基準のままだとJSTで日付が変わってから午前9時になるまでの間、「本日の使用量」が前日のまま表示され続ける不具合があった（issue #71）
- **ダッシュボードへのデータ提供方式**: オーケストレータが最小限のHTTPサーバー（`http.server.ThreadingHTTPServer`、デフォルト `http://127.0.0.1:8787`）で `GET /api/state` を提供する。ポーリングスレッドが集約するたびに最新状態を更新し、リクエスト時点の最新値を `{"decisions": [...], "reviews": [...], "project_status": [...], "status_counts": {...}}` 形式のJSONで返す。[2-3](#2-3-指示出しapi内部api)の指示出し（POST）も同じサーバーに追加する想定
- **指示出し操作直後の同期更新**: [2-3](#2-3-指示出しapi内部api)の`POST /api/projects/{repo}/issues/{issue_number}/instruct`・`POST /api/projects/{repo}/issues`がGitHub側の変更（ラベル・コメント・PRマージ等）に成功した直後、レスポンスを返す前に本節のポーリング1回分（`orchestrator/orchestrator/polling.py`の`poll_once`）を同期的に実行し、その結果でこのキャッシュを更新する。上記5分間隔の背景ポーリングだけに頼ると、ダッシュボードが操作直後に`GET /api/state`を再取得しても最大5分間は古いスナップショットが返り続け、操作対象のissueがまだ一覧に残っているように見えて二重操作できてしまう不具合があった（issue #70）。この同期更新自体が失敗しても、既に成功している指示操作のレスポンスは成功のまま返し、最新化は次回の背景ポーリングに委ねる。

### 2-3. 指示出しAPI（内部API）

ダッシュボード（Next.js）とオーケストレータ間の内部APIは以下の通り。既存issueへの指示（承認・自由記述）と、新規タスク（新規issue）の作成の2系統を持つ。

#### 既存issueへの指示

```
POST /api/projects/{repo}/issues/{issue_number}/instruct
Content-Type: application/json

{
  "action": "approve" | "instruct",
  "message": "string（省略時はaction種別に応じた定型文を使用）"
}
```

- `approve`: 定型文「承認します。進めてください。」をissueにコメント投稿する。想定対象は `needs-human-decision` のissue。
- `approve`（対象issueが`status:in-review`の場合）: 上記のコメント投稿・ディスパッチの経路には乗らず、紐づくPRのsquash merge（`gh pr merge --squash`）のみを行う特別処理となる（issue #58、`orchestrator/orchestrator/instruct.py`の`handle_instruct`）。マージ成功後は`gh issue close`でissueを明示的にクローズする（PR本文の`Closes #`によるGitHubの自動クローズは、そのPRがリポジトリの**デフォルトブランチ**にマージされた場合のみ発動する仕様であり、本プロジェクトのワークフロー（[開発ワークフロー](../CLAUDE.md)、PRは`develop`にマージ）では発動しないため、明示的なクローズを行わないとissueが開いたまま残る不具合が実際に発生した）。issueクローズに続けて、ラベルも`status:in-review`から`status:closed`へ即時遷移させる（`transition_label`）。これを省き背景ポーリング（`close_watcher.py`、5分間隔）でのラベル更新のみに委ねると、承認直後の[2-2「指示出し操作直後の同期更新」](#2-2-データ取得仕様ポーリング)時点ではまだ`status:in-review`のままのため、レビュー待ち一覧の判定（ラベルのみを見る）からカードが即座には消えない不具合になる（issue #70フォローアップ）。ラベル遷移に続けて、マージ済みPRのheadブランチ（`feature/*`）も`gh api -X DELETE repos/{repo}/git/refs/heads/{branch}`で削除する（issue #72）。ブランチ削除はマージ・issueクローズ成功後の後始末に過ぎないため、`gh pr merge --squash --delete-branch`のようにマージと同一コマンドには含めず分離したステップとし、削除の失敗（保護ブランチ設定・既に削除済み等）は握りつぶしてログ出力のみに留める（マージ・issueクローズが既に成功している以上、承認レスポンスとしては成功を返す。`--delete-branch`を同一コマンドに含めた場合、ブランチ削除だけの失敗でコマンド全体が非0終了扱いとなり後続の`close_issue`が実行されなくなる、というissue #58と同種の不具合を再発させるリスクがあるため）。
  - **紐づくPRの解決方法**: `gh api repos/{repo}/issues/{issue_number}/timeline`のタイムラインイベントから`event == "cross-referenced"`かつPRであるものを収集し、**最後（最新）にcross-referenceされた1件だけ**を対象とする（`github_client.resolve_pr_number`）。同一issueに複数のPRが紐づいている場合、承認操作はその最後の1件のみをマージ・クローズ・ブランチ削除対象とし、**それ以外のPRには一切処理を行わない**（マージもされず、エラーや警告も出ない）。この判定は`Closes #`等のクローズキーワードの有無を見ておらず単なる`#<issue番号>`への言及でもcross-referenceイベントは発生するため、無関係な参照用PRが「最新」として誤って選ばれる可能性がある。ダッシュボードのレビュー待ちカードに表示されるPRリンクチップ（[2-4](#2-4-ダッシュボードの画面設計)）も同じ関数の解決結果を使うため、表示されているPRと実際に承認時にマージされるPRは常に一致する。
    - **既知の注意点（cross-referenceイベントが生成されないケース）**: issue番号の直後に半角スペース・改行・句読点等の区切り文字を挟まず日本語テキストが続く形（`#77で`、`#77の`、`#77を`等）だと、GitHub側の自動リンク解析がissue参照として認識せず、cross-referenceイベントが生成されないことを実例で確認している（issue #82、PR #81本文の`issue #77で報告された...`）。Agent Runnerが日本語でPR本文を書く際に助詞が数字の直後へ続くのはごく自然な書き方であり、構造的に再発しやすい。そのためAgent Runner起動時、`--append-system-prompt`でPR本文に`Closes #<issue番号>`を独立行として書くよう明示的に指示している（`orchestrator/orchestrator/agent_runner.py`の`AGENT_RUNNER_PR_ISSUE_REFERENCE_INSTRUCTION`）。
    - **フォールバック（OPEN PR本文検索）**: 上記の理由等でcross-referenceイベントが1件も見つからない場合、`resolve_pr_number`は対象リポジトリのOPEN PR一覧（`gh pr list --repo {repo} --state open --json number,title,body,updatedAt`）を取得し、タイトル・本文中に`#{issue_number}`が**直後に別の数字が続かない**形（`#770`等の別issue番号との誤マッチを避ける）で含まれるPRを検索する（`github_client._resolve_pr_number_from_open_prs`）。複数件ヒットする場合はcross-reference方式と同じ方針で最も更新が新しいものを採用する。この方式はGitHub側のissue参照パーサーのCJK境界問題に依存せず、Unicode文字列として素直に`#<issue番号>`を探すため、日本語直後の参照でも検出できる。ただし、無関係な参照用PRを誤検出し得る限界はcross-reference方式と同水準で残る。
    - **既知の注意点（issue参照自体が皆無なケース）**: `AGENT_RUNNER_PR_ISSUE_REFERENCE_INSTRUCTION`はAgent Runnerの自己申告に委ねる運用のため、指示自体が守られずPR本文にissue番号への言及が一切含まれないケースが実例で発生した（issue #144、issue #136 / PR #143）。この場合cross-reference方式・OPEN PR本文検索のどちらでも救えない。そのため`agent_runner.run_agent_runner`の正常終了処理側（[3章](#3-agent-runner連携設計)）に、issue #78のラベル遷移漏れ検知と同様の決定的フォールバックを追加している。正常終了時点でissueが`status:in-review`に到達しているにもかかわらず`resolve_pr_number`が`None`を返す場合、Agent Runnerセッション終了時点のworktreeのカレントブランチ（`git -C {worktree_path} rev-parse --abbrev-ref HEAD`）をheadとするOPEN PRを`gh pr list --head {branch} --state open`で検索し（`github_client.find_open_pr_by_branch`）、1件に特定できればそのPR本文へ`Closes #<issue番号>`を追記する（`github_client.append_pr_issue_reference`、本文は上書きではなく既存本文への追記）。これによりGitHub側のcross-referenceイベントが新たに生成され、以降のポーリングでは通常の解決経路でも解決できるようになる。ブランチからも一意にPRを特定できない場合はログ警告に留め、`needs-human-decision`への強制遷移は行わない（PR自体は既に作成されておりissueの状態遷移自体は正しく、PRリンク表示のみが欠けるにとどまるため）。
  - **削除対象ブランチの制約**: 削除するのはPRのhead（マージされる側の`feature/*`ブランチ）であり、マージ先の`develop`が誤って削除されることはない。ただし同一ブランチから複数のPRが作られている場合（通常のAgent Runner運用では発生しない想定）、削除すると他のPRが壊れる可能性がある点は既知の制約として残る。
  - **ローカルworktreeの同期**: 上記のブランチ削除はGitHub側（リモート）のみに対する操作であり、そのままではAgent Runner実行用のローカルgit worktree（[2-1](#2-1-対象リポジトリ一覧の管理)の`worktree_path`）が削除済みブランチをチェックアウトしたまま残ってしまう（issue #80）。そのためブランチ削除が成功した場合に限り、`orchestrator/orchestrator/worktree.py`の`sync_worktree_after_branch_delete`を呼び出し、対象worktreeを`git fetch origin develop` → `git checkout --detach origin/develop`（**ブランチ名`develop`ではなくdetached HEAD**で最新の内容に合わせる） → 削除済みブランチの`git branch -D`の順に同期する。detached HEADにしているのは、Agent Runner用worktreeとオーケストレータ自身のソースディレクトリが同一リポジトリのlinked worktreeであり、オーケストレータ側が常時`develop`ブランチをチェックアウト済みのため、Agent Runner用worktree側で`develop`という**ブランチ名**をチェックアウトしようとするとgitの「同じブランチを複数worktreeで同時チェックアウトできない」制約に必ず抵触して失敗するためである（issue #88、当初`git checkout develop`としていたところ本番環境で常に失敗することが判明し修正）。`fetch`・`checkout`が失敗する場合（ネットワーク不調・未コミットの変更が残っている等）はそれ以降の処理を行わずログ警告のみに留め、この処理自体の失敗は承認レスポンスの成功に影響しない（ブランチ削除失敗時と同様の握りつぶし方針）。また、[2-3「プロジェクト単位のディスパッチキュー」](#プロジェクト単位のディスパッチキュー)の`DispatchQueue.is_running(repo)`が真の間（＝同一プロジェクトの別issueでAgent Runnerが実行中の間）は、実行中セッションの作業ディレクトリを横から書き換えないようこの同期処理自体をスキップする。
- `instruct`: ダッシュボードのテキストボックスから入力した**自由記述のメッセージ**をコメント投稿する。issueの状態を問わず送信可能（作業中issueへの割り込み指示を含む）。
- `approve`/`instruct` はいずれも、[1章「自由記述指示によるラベル遷移ルール」](#自由記述指示によるラベル遷移ルール)に従ってラベルを更新した上で、[3章](#3-agent-runner連携設計)のAgent Runnerディスパッチを行う（対象プロジェクトが実行中でなければ即時、実行中ならプロジェクト単位のキューに追加し実行完了後に処理）。上記の`status:in-review`での`approve`はこの限りではない。
- 却下（差し戻し）操作は設けない。判断待ちのissueに対して人間が取れる操作は「承認」と「自由記述での指示」のみとする。方針を変えたい場合も、却下という専用アクションではなく自由記述（`instruct`）でその旨を伝える（issue #55の設計検討で、`reject`は`instruct`と同様コメント投稿する点は同じで、ディスパッチせずAgent Runnerを起こさないだけの違いしかなく、UI上の区別も誤操作の元になるため廃止）。

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
- ただし対象issueがクローズ済み（`status:closed`）の場合は、新規コメントを検知してもディスパッチしない。クローズ済みissueへの指示（再着手）はダッシュボードの指示APIによる明示的な操作でのみ受け付ける。これを設けないと、PRマージに伴うissueクローズと同時に投稿した説明コメント（作業再開の意図がないもの）を指示と誤検知し、Agent Runnerを不要に再起動させてしまう（issue #45・#51）。

#### プロジェクト単位のディスパッチキュー

- オーケストレータはプロジェクトごとに実行中フラグ（ロック）を持つ。
- `instruct`（`approve`含む）または `dispatch: "immediate"` の新規issue作成のリクエストが届いた際、対象プロジェクトが実行中でなければ[3章](#3-agent-runner連携設計)のディスパッチを即座に行う。
- 実行中であれば、そのメッセージ（issue番号・コメント本文）をプロジェクトごとのFIFOキューに追加する。実行中の `claude -p` プロセスが終了次第、キューの先頭のメッセージで次のディスパッチを `--resume` 付きで行う。複数メッセージが溜まっている場合は1つずつ順に処理する。
- `DispatchQueue.is_running(repo)`（プロジェクト単位の実行中判定）に加え、`DispatchQueue.is_active(repo, issue_number)`でissue単位の実行中・待機中判定ができる（[2-2「孤立したin-progress検知」](#2-2-データ取得仕様ポーリング)、issue #50）。

### 2-4. ダッシュボードの画面設計

視覚的な画面設計（レイアウト、ワイヤーフレーム、スタイル）は本書では扱わず、Claude Designへの指示プロンプトとして[design-prompt-dashboard.md](./design-prompt-dashboard.md)にまとめている。表示すべきデータ項目・操作は[2-2](#2-2-データ取得仕様ポーリング)・[2-3](#2-3-指示出しapi内部api)の仕様に準拠する。

## 3. Agent Runner連携設計

### 3-1. 起動パラメータ

```bash
claude -p "<指示内容>" \
  --output-format stream-json --verbose \
  --dangerously-skip-permissions \
  --chrome \
  --append-system-prompt "<ラベル自己管理指示>" \
  (--session-id <new-uuid> | --resume <session-id>)
```

- worktreeディレクトリの指定はCLIフラグではなく、Pythonの `subprocess.Popen(..., cwd=<worktree-path>)` で行う（実際の `claude` CLIに `--cwd` フラグは存在しないため。`--add-dir` は追加の許可ディレクトリ指定であり用途が異なる）。
- `<session-id>` は `config/sessions.json`（`.gitignore`対象、コミットしない）に**issueごと**に保存する（`"{repo}#{issue_number}": "<session-id>"`、`orchestrator/orchestrator/session_store.py`）。初回ディスパッチ時はオーケストレータが `uuid.uuid4()` を生成し `--session-id` で明示的に指定してセッションを新規作成する。生成したIDを `config/sessions.json` に書き込み、同一issueへの以降の指示では `--resume <session-id>` で再開する。
  - **プロジェクト単位ではなくissue単位である理由**: 当初はプロジェクト（リポジトリ）単位で1つのセッションIDのみを`config/projects.yaml`に保存していたが、この場合同一プロジェクト内の全issueが1本のClaude Code会話を共有してしまう。あるissueが`needs-human-decision`で停止している間に別issueが同じセッションで進行・完了すると、後から前者issueを`--resume`で再開した際、セッションの直近の会話文脈（別issueの完了報告）を引きずってしまい、再開したissue本来の内容に取り組まれない不具合が発生した（issue #32）。issueごとに独立したセッションを持つことで、他issueの進行状況に文脈が左右されないようにする。
- `--output-format stream-json --verbose` により、実行結果をツール呼び出し・メッセージ単位のNDJSON（1行1JSON）として逐次標準出力に取得する。`--verbose` は `-p`（非対話モード）で `stream-json` を使う場合にCLIが必須とするフラグ。ストリームの最後に出力される `"type":"result"` のイベント（`result` フィールド等を含む）を3-2のissueコメント要約に利用する。当初は `--output-format json`（完了後に最終結果のみを一括出力）を使っていたが、この形式ではプロセス終了まで標準出力に一切何も書き出されず、実行時間の長いタスク（数十分〜）では「ログファイルが更新されない状態」が続き、実行中の進捗を外部から確認する手段が無かったため変更した（issue #49）。
- `--append-system-prompt` により、[1章](#1-データモデル状態遷移設計)でAgent Runner自身の責務とした`needs-human-decision`・`status:in-review`へのラベル自己付与（対象issue番号・リポジトリ名・具体的な`gh issue edit`コマンドを含む）を、指示内容の文面によらず毎回明示する（`agent_runner.py`の`AGENT_RUNNER_LABEL_INSTRUCTION`）。当初この指示が無く、PR作成後もラベルが`status:in-progress`のまま遷移しない事例が発生したため導入した（issue #33）。
- 同様に`--append-system-prompt`で、Agent Runnerが調査結果の報告等の目的で`gh issue comment`等を用いてissueに直接コメントを投稿する場合は、本文末尾に`github_client.BOT_COMMENT_MARKER`（`<!-- producer-desk:bot-comment -->`）を必ず付与するよう毎回明示する（`agent_runner.py`の`AGENT_RUNNER_COMMENT_MARKER_INSTRUCTION`）。オーケストレータ内部の通知処理（`github_client.post_comment`）はこのマーカーを自動付与するが、Agent Runner自身が`gh`コマンドを生で叩く経路はこの仕組みを経由しないため付与漏れが起こり得る。マーカーが無いと[2-3「共通仕様」](#共通仕様)のコメント監視処理（`comment_watcher.py`）が自分自身の投稿を人間からの新規指示と誤検知し、同一内容を無限に再ディスパッチしてしまう（ラベルも`needs-human-decision`→`status:in-progress`に巻き戻る。issue #43）。
- 同じ指示（`AGENT_RUNNER_COMMENT_MARKER_INSTRUCTION`）内で、セッション終了時の最終応答は3-2の通り`run_agent_runner`が自動的に「Agent Runner実行結果:」というissueコメントとして無条件に投稿する旨も明示し、対応完了時にAgent Runner自身が重ねて完了報告コメントを投稿する必要はないことを伝える。能動的なissueコメント投稿は、長時間かかる作業の途中経過報告など、最終応答を待たずに人間へ可視化する価値がある場合に限定する。当初この案内が無かったため、AI自身の能動的な完了報告コメントと、オーケストレータによる無条件の自動投稿とがほぼ同時刻・同内容で重複して投稿される事例が複数のissueで発生した（issue #84）。
- 同様に`--append-system-prompt`で、ダッシュボードのUI実装時はCLAUDE.md記載のClaude DesignのURL（`https://claude.ai/design/...`）の実ソースを`DesignSync` MCP（`get_project`/`list_files`/`get_file`、`projectId`はURLの`/p/<uuid>`部分）で直接取得し、配色・余白等の実際のCSS/JS値を確認してから実装するよう毎回明示する（`agent_runner.py`の`AGENT_RUNNER_DESIGN_VERIFICATION_INSTRUCTION`）。デザインURLは認証必須で`WebFetch`では取得できず（403）、テキストの設計文書にも色・アイコンの指定は無いため導入した（issue #33）。当初はブラウザ操作ツールでの目視確認のみを指示していたが、キャンバス上の要素クリックによるコード選択が自動操作から機能しない・プレビューが状態を持つインタラクション（ダイアログ表示等）を再現しない静的スナップショットである等の理由で、目視確認だけでは細部の再現性に限界があることが判明し、`DesignSync`による直接取得を主手段に切り替えた（issue #55・PR #57）。
- `DesignSync`が権限不足等で使えない場合はフォールバックしない。ブラウザ操作ツールでの代替取得（チャットへの問い合わせ等）は不正確になりうるため`DesignSync`の代替にはせず、その旨を実行結果コメントに明記してその場で作業を停止し、`needs-human-decision`として人間の確認を仰ぐ。`DesignSync`で値を取得できた場合、実装後はブラウザ操作ツール（`mcp__claude-in-chrome__*`）で完成品とデザインのプレビューを並べて最終的な見た目の一致を確認する（これは数値の取得手段ではなく完成後のセルフレビュー用途）。
- `--chrome` フラグにより、Claude in Chrome連携を明示的に有効化する。`claude -p`（非対話モード）はこの連携がデフォルト無効で、フラグなしでは`mcp__claude-in-chrome__*`ツール自体が存在せず、上記の実装後確認が機能しない（issue #33の追加原因調査で判明）。
  - **運用上の前提**: `DesignSync`の利用には`claude.ai`ログインへのデザインシステムアクセス権限が必要。**この権限は一度`/design-login`（または通常のclaude.aiログインでのデザインアクセス許可）を実行すればmacOSキーチェーン（サービス名`Claude Code-credentials`）に永続化され、同一ホスト・同一OSユーザーで動く以降の`claude` CLI呼び出し（Agent Runnerの`claude -p`を含む）から自動的に利用できる。** そのためAgent Runner自身が実行時に認証フロー（ブラウザでのOAuth同意等、人間の操作が必要な手順）を行うことはできないし、行う必要もない。運用開始前にホスト上で一度だけ人間が`/design-login`を実行しておけば、以降のAgent Runner実行では追加の認証操作なしに`DesignSync`が使える想定（Chrome連携時の「事前にログイン状態を維持しておく」運用と同じパターン）。実行時に権限が無い場合、Agent Runnerはその旨を実行結果コメントに明記し、`needs-human-decision`として人間の確認を仰ぐ。

### 3-2. 監視方法

- **ヘルスチェック**: ワンショット実行のため常時稼働のプロセス監視（ヘルスチェックエンドポイント等）は設けない。プロセスの終了コード（0=正常終了、非0=異常終了）を確認する。異常終了時はissueにコメントを投稿し、`needs-human-decision` ラベルに遷移させて人間の確認を促す（正常終了時のラベル遷移は、Agent Runner自身が実行中に `gh` コマンドで行う自己付与を第一とする。[1章](#1-データモデル状態遷移設計)参照）。**実行中の進捗確認は、プロセス監視ではなく後述のログ収集（`tail -f`によるリアルタイム追跡）で行う（issue #49）。**
  - **異常終了時のコメント文面**: 異常終了は大抵の場合APIリミット到達（429）が原因であり、その場合は終了コード・ログパスを提示しても人間が読むべき情報にならない（issue #146）。`run_agent_runner`はNDJSON出力の最後の`"type":"result"`イベント（`_parse_result_payload`、利用量記録用の`_extract_usage_records`と共通の抽出処理`_classify_run_error`（issue #60）を経由）から`is_error`/`api_error_status`を参照し、`api_error_status == 429`かつ`usage_store.parse_limit_reset_text()`で`result`の自由文から解除予定時刻（例: `resets 1pm (Asia/Tokyo)`）を抜き出せた場合に限り、「Claude CodeのAPI利用リミットに達したため停止しました」という趣旨のメッセージ（解除予定時刻付き）に切り替える（`agent_runner.py`の`_build_failure_comment`）。**429到達時でも`result`が空・非文字列で解除予定時刻等の情報が一切得られない場合は、情報量ゼロのメッセージにするより従来通り終了コード・ログパスを含むメッセージにフォールバックする**（429以外の異常終了・予期しない例外等も同様）。いずれの場合も`needs-human-decision`へのラベル遷移自体は変わらない。
- **正常終了時の決定的フォールバック**: プロセスが正常終了（exit 0）しても、Agent Runnerが上記の自己申告ラベル遷移（`AGENT_RUNNER_LABEL_INSTRUCTION`）を実行し忘れることがある（issue #70）。正常終了時、issueは必ず「PR作成済み（`status:in-review`）」「人間への確認が必要（`needs-human-decision`）」のいずれかに到達している設計であるため、オーケストレータは`run_agent_runner`の成功分岐でissueコメント投稿後に現在のラベルを再取得し、`status:in-progress`のまま変化していなければ（＝`needs-human-decision`・`status:in-review`いずれにも自己遷移していなければ）常に異常とみなし、`needs-human-decision`へ強制的に遷移させる（`result`テキストの自然文判定は行わない。既存の「異常終了時は`needs-human-decision`に強制遷移」ロジックと対称的な構造。issue #78）。Agent Runnerが既に自己遷移済みの場合、`transition_label`の冪等性によりこのフォールバックは何も行わない。
- **ログ収集**: ログファイル（`logs/<repo>/<timestamp>.log`、`<timestamp>`はJST基準の`%Y%m%dT%H%M%S`。UTC基準・末尾`Z`表記だった旧形式から、`usage_store.py`の`_JST`と同じ前例に合わせて変更した。issue #114）はディスパッチ開始時点で作成し、以降は `claude` CLIの標準出力（NDJSON、3-1参照）を1行読むたびに都度ファイルへappendする（`agent_runner.py`の`_stream_process_output`。`subprocess.Popen`でプロセスを起動し、完了を待たずに読み取りを進める）。標準エラー出力は `stderr=subprocess.STDOUT` で標準出力ストリームに合流させ、取りこぼしを防ぐ（別スレッドでの並行読み取りは実装が複雑になる割に効果が変わらないため採用しなかった）。この方式により、実行中に `tail -f logs/<repo>/<timestamp>.log` でリアルタイムに進捗を追える（issue #49。旧方式では `subprocess.run(capture_output=True)` でプロセス終了まで標準出力・標準エラーをメモリにバッファし、終了後に一度だけログファイルへ書き出していたため、実行時間の長いタスクでは終了までログファイルが一切更新されなかった）。加えて、プロセス終了後にNDJSON全体から最後の `"type":"result"` イベントを取り出し（`_parse_result_payload`）、その `result` フィールドを要約としてissueコメントに投稿し、ダッシュボードのプロジェクト状況表示と連動させる。
- **個別実行ログの保持クリーンアップ**: 「1実行＝1ファイル、実行完了まで同一ファイルへ追記」という書き込み方式自体は変更しない（NDJSONの一貫性・`tail -f`の継続性を壊さないため）。`run_agent_runner`の実行完了直後（正常終了・異常終了・worktree不在による早期リターンいずれの場合も）に、`agent_runner.py`の`cleanup_old_agent_logs`が当該リポジトリの`logs/<repo>/`配下を走査し、**更新日時（mtime）**が`log_retention_days`（2-1の`config/projects.yaml`設定値、既定7日）より古い`*.log`ファイルのみを削除する。ファイル名に埋め込まれた実行開始時刻ではなくmtimeで判定するのは、`_stream_process_output`が1行書くたびに`flush()`するため実行中のファイルは常にmtimeが「今」に近く、実行中は経過日数のカウントが始まらないため（`DispatchQueue.is_active()`等の別途のフラグ管理は不要。issue #114）。

### 3-3. オーケストレータ⇔Agent Runnerのインターフェース仕様

- オーケストレータはPythonの `subprocess`（`Popen`）でClaude Code CLIを直接起動し、標準出力を逐次読み取りながら、プロセス終了時に終了コードを取得する（HTTP等の別プロセス間APIは設けない）。ディスパッチ元の`dispatch_fn`から見た`run_agent_runner`の呼び出し自体は同期的（プロセスの完了を待って戻る）であり、この点は`--output-format json`を使っていた旧方式から変わらない（issue #49で変更したのはCLIの出力形式とログ書き出しタイミングのみで、呼び出し側インターフェースは維持）。
- 1プロジェクトにつき同時に1つの `claude -p` プロセスのみ実行する（同一worktreeへの同時書き込みを避けるため、ディスパッチ中は当該プロジェクトの新規ディスパッチをキューイングする。キューの詳細は[2-3「プロジェクト単位のディスパッチキュー」](#プロジェクト単位のディスパッチキュー)参照）。

### 3-4. オーケストレータ自身のログ出力設計

`server.py`・`aggregation.py`・`instruct.py`・`worktree.py`・`agent_runner.py`は`logging.getLogger(__name__)`でロガーを取得するのみで、ハンドラ・フォーマッタ・レベルの設定（`logging.basicConfig()`相当）は`main.py`の`main()`冒頭で一度だけ呼ぶ`orchestrator/orchestrator/logging_config.py`の`configure_logging()`に集約する（issue #114。以前はこの設定が無く、Pythonのデフォルト（レベル`WARNING`以上）で出力されていたため、`logger.info()`/`logger.debug()`が実質握りつぶされていた）。

- **フォーマット**: `logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")`。`%(asctime)s`はOSのタイムゾーン設定に依存しないよう、`formatTime`をオーバーライドしてJST（`Asia/Tokyo`）基準に固定する（`usage_store.py`の`_JST`と同じJST定義を`orchestrator/timezone.py`に切り出し共有する）。
- **レベル制御**: 環境変数`ORCHESTRATOR_ENV`で切り替える。未設定時は`production`扱いで`INFO`以上のみ、`development`指定時は`DEBUG`以上（全レベル）を出力する。`bin/start.sh`はこの変数を明示的に設定せず起動するため、運用時は常に`production`相当となる。
- **ローテーション**: `logging.handlers.TimedRotatingFileHandler(log_path, when="midnight", backupCount=log_retention_days)`で`logs/orchestrator.log`に直接書き込む（`log_retention_days`は2-1の`config/projects.yaml`設定値、既定7日。自前でのファイル走査・削除は実装せず標準機能に委譲する）。二重書き込みを避けるため、コンソール向けの`StreamHandler`は追加しない。`bin/start.sh`側の`nohup ... >>"${ORCHESTRATOR_FALLBACK_LOG}" 2>&1`という生リダイレクトは、ロガーを経由しない出力（`configure_logging()`呼び出し前のクラッシュ・未捕捉例外のトレースバック等）を取りこぼさないための最終フォールバックとして残すが、書き込み先は`logs/orchestrator.stderr.log`という別ファイルに分離する。`TimedRotatingFileHandler`はローテーション時に`orchestrator.log`を`orchestrator.log.YYYY-MM-DD`へ**rename**した上で新規に`orchestrator.log`を開き直すため、シェル側の`nohup`が同じパスに`>>`で開いたファイルディスクリプタを共有すると、rename後もシェル側は旧inode（rename後の名前）へ書き込み続けてしまう。この状態でPython側がbackupCount超過分のバックアップファイルを`unlink`しても、シェル側のfdが開いたままならディスク上の実体は解放されず、ディレクトリ上は見えないまま際限なく肥大化する（issue #114が解消しようとした問題を別の場所で再発させる）。この競合を避けるため、両者の書き込み先パスを分離した。
- **`main.py`の`print()`置き換え**: 起動時メッセージ（読み込んだプロジェクト一覧・APIサーバーのURL等）はすべて`logger`経由に置き換え、上記4ファイル・`agent_runner.py`と同一の出力系統・フォーマットに統一する。

## 4. モデルルーター設定設計

[アーキテクチャ設計書 5章](./architecture.md#5-モデルルーティング)の通り、自走タスク本体はLiteLLM Proxy等のモデルルーティング層を導入せず、Claude Code CLIを直接利用する。ローカルLLMの補助的併用（コードレビュー支援・デバッグ調査の下調べ・日本語ドキュメント生成）についても、モデルルーティング層は追加せず、Agent Runner（Claude Code CLI）が起動時に受け取る指示に従って自身で呼び出す構成とする。モデルの利用可否確認はMCP `ollama-client`でよいが、実際の生成呼び出しは後述の「手動ベンチマーク・本番経路共用ツール（`ollama_bench.py`）」節で説明する`ollama-bench`コマンド経由でOllama REST APIを直接呼び出す（issue #107、詳細は後述）。

### タスク種別ごとの推奨モデル

[要件定義書 2-5](./requirements.md#2-5-モデル選択方針)の調査結果（`research-log` [`local-llm-benchmark`](https://github.com/nosetech/research-log/blob/main/log/2026/08/local-llm-benchmark/README.md) / [`local-llm-benchmark-additional`](https://github.com/nosetech/research-log/blob/main/log/2026/08/local-llm-benchmark-additional/README.md)）に基づき、以下を論理的な対応表とする。設定ファイルとしては永続化せず、後述のsystem prompt文字列にハードコードする（利用モデル数が少なく、対応表の変更頻度も低いため設定ファイル化のコストに見合わないと判断）。

| タスク種別 | 推奨モデル | 選定理由 |
| --- | --- | --- |
| コードレビュー支援 | `deepseek-coder-v2:16b` | 検証6モデル中、指摘の網羅性・日本語安定性・実装可能な修正提案のバランスが最良 |
| デバッグ調査の下調べ | `deepseek-coder-v2:16b` | 原因特定と動作する修正コードの提示を両立できる唯一のモデル |
| 日本語ドキュメント生成 | `gemma2` | 中国語混入がなく日本語の一貫性が最も高い（未直接検証のため実運用開始時に品質を再確認する） |
| 上記以外・速度優先の簡易チェック | `qwen2.5-coder:7b` | VRAM内に収まる7B級モデルの中で最速（76〜79 tok/s帯） |

`granite-code:8b`（日本語出力が意味不明な単語の反復・スペイン語化に陥る）・`codestral:22b`（VRAM超過で4.6 tok/sまで速度低下）は不採用とする。

### 実装方針: Agent Runnerへのsystem prompt指示

- オーケストレータ（`orchestrator/orchestrator/agent_runner.py`）はモデル選択ロジックを持たない。既存の`AGENT_RUNNER_LABEL_INSTRUCTION`・`AGENT_RUNNER_DESIGN_VERIFICATION_INSTRUCTION`と同様に、`AGENT_RUNNER_LOCAL_LLM_INSTRUCTION`定数として上記対応表を`--append-system-prompt`で毎回Agent Runnerに渡す。system prompt生成時に呼び出し元の`repo`/`issue_number`を埋め込み、後述の`ollama-bench --record`の引数として使わせる。`ollama-bench`はオーケストレータ自身のvenvにのみインストールされたコンソールスクリプトで、Agent Runnerが担当するプロジェクトのworktree（producer-desk自身とは別リポジトリのことが多い）のPATHには存在しないため、バレのコマンド名では解決できない。解決済みの絶対パス（`_resolve_ollama_bench_path`が解決）をsystem prompt本文に埋め込む方式は、長いパスを複数回のBashツール呼び出しにまたがってAgent Runnerが書き写す必要があり写し間違いを誘発しやすいため採らず、`run_agent_runner`が子プロセス（`claude -p`本体、およびそのBashツールが起動するシェル）の環境変数`OLLAMA_BENCH_PATH`として渡す。Agent Runnerは`"$OLLAMA_BENCH_PATH"`という短い参照だけを覚えればよい。子プロセスのPATH自体は書き換えない（対象プロジェクト自身の`python`/`pytest`/`ruff`等をオーケストレータ側のものへ誤ってシャドーイングする恐れがあるため）。
- Agent Runnerは、コードレビュー支援・デバッグ調査の下調べ・日本語ドキュメント生成が必要になった場面で、指示に従いローカルLLMを自身の判断で呼び出す。呼び出すか否か、結果をどう扱うかもAgent Runnerの裁量とし、オーケストレータ側での結果ハンドリングは行わない（Agent Runner内で完結する）。モデルの利用可否確認は`mcp__ollama-client__ollama_list`/`ollama_ps`等のMCPツールでよいが、実際に生成させる呼び出しは次節の`ollama-bench`コマンド（Bashツール）を使い、MCP `mcp__ollama-client__ollama_chat`は使わない。
- 自走タスク本体（コード変更そのもの）にはローカルLLMの出力をそのまま採用せず、Function Callingの信頼性が確認されているClaude Code自身が最終的な変更を行う（[要件定義書 2-5](./requirements.md#2-5-モデル選択方針)の方針を踏襲）。

### 手動ベンチマーク・本番経路共用ツール（`ollama_bench.py`）

MCP `ollama-client`（サードパーティ`ollama-mcp`パッケージ）の`ollama_chat`ツールは、Ollama REST APIレスポンスから`message.content`のみを抽出して返す実装になっており、`prompt_eval_count`/`eval_count`/`total_duration`等のメトリクスを破棄する。そのため、MCP経由でAgent Runnerがローカルモデルを呼び出しても利用量を記録できない。

当初はモデル選定・性能検証を人間が手動で行う際の実測値取得専用ツールとして`orchestrator/orchestrator/ollama_bench.py`（`ollama-bench`コマンド、Ollama REST API `POST /api/chat`、`stream: false`を直接呼び出す。[アーキテクチャ設計書 5章](./architecture.md#5-モデルルーティング)参照）を追加した（issue #60）。issue #107で、Agent Runner本番経路のローカルLLM生成呼び出しもこのツールに一本化し、本番の利用量もダッシュボードに反映されるようにした。

- 接続先はOllama公式CLIと同じ環境変数`OLLAMA_HOST`（未設定時は`http://127.0.0.1:11434`）から解決する。`--host`引数で明示的に上書きもできる。
- `--record --repo <repo> --issue-number <n>`を付けると、計測結果（`model`・`input_tokens`・`output_tokens`・`duration_seconds`）を[2-2](#2-2-データ取得仕様ポーリング)の`usage_store.py`経由で`config/usage.db`に統合して記録する。Claude Code実行分の記録では`duration_seconds`は常に`None`になる（Agent Runnerの実行結果JSONには処理時間が含まれないため）。
- `--format json`を付けると、Ollama REST APIに構造化JSON出力を要求する（コードレビュー支援等でJSON形式のレビュー結果を受け取りたい場合に使う。任意）。
- Agent Runner本番経路では`AGENT_RUNNER_LOCAL_LLM_INSTRUCTION`が`--record --repo {repo} --issue-number {issue_number}`付きでの呼び出しを指示する（`orchestrator/orchestrator/agent_runner.py`）。オーケストレータのポーリングループ自体からは呼び出さない（呼び出すのはあくまでAgent Runner=Claude Code CLIプロセス自身）。

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

**承認・自由記述（既存issueへの指示）**

1. プロデューサーがダッシュボードで対象issueの「承認」ボタン（押下後Yes/No確認）、または自由記述の指示入力欄からメッセージを送信する。
2. ダッシュボードが[2-3](#2-3-指示出しapi内部api)の内部API（`action: "approve" | "instruct"`）にリクエストを送信する。
3. オーケストレータが対象issueの現在のラベルを取得する（[1章](#1-データモデル状態遷移設計)の冪等フロー）。
4. `gh api` 経由でissueに定型コメント（承認）または自由記述メッセージ（instruct）を投稿する。
5. [1章「自由記述指示によるラベル遷移ルール」](#自由記述指示によるラベル遷移ルール)に従いラベルを更新し、対象プロジェクトが実行中でなければ[3章](#3-agent-runner連携設計)のAgent Runnerディスパッチを即時実行、実行中なら[2-3「プロジェクト単位のディスパッチキュー」](#プロジェクト単位のディスパッチキュー)に追加する。
6. 上記が成功した直後、レスポンスを返す前に[2-2「指示出し操作直後の同期更新」](#2-2-データ取得仕様ポーリング)の通り`poll_once`を同期実行し、`GET /api/state`が返すキャッシュを最新化する（issue #70）。
7. 処理結果をダッシュボードのレスポンスとして返す。ダッシュボード側（`Dashboard.tsx`の`refresh`）はこのレスポンス到達後に`GET /api/state`を再取得し、その完了を待ってから対象カードの「承認」「返信」ボタンを再度操作可能に戻す。これにより、6で最新化済みの一覧が反映されるまでは同一issueへの二重操作ができない。

対象issueが`status:in-review`の状態で「承認」した場合はこのフローに乗らず、[2-3「既存issueへの指示」](#既存issueへの指示)記載の通り紐づくPRのsquash merge・issueクローズ・`status:closed`へのラベル遷移・headブランチ削除のみを行う特別処理となる（コメント投稿・Agent Runnerディスパッチは行わない）。この場合も上記6・7の同期更新・再取得完了待ちは同様に適用される。

**新規タスク（新規issue）の作成**

1. プロデューサーがダッシュボードでプロジェクトを選択し、タイトルと自由記述のプロンプトを入力、即時着手／todo登録を選んで送信する。
2. ダッシュボードが[2-3](#2-3-指示出しapi内部api)の新規issue作成APIにリクエストを送信する。
3. オーケストレータが `gh api` 経由でissueを作成し、`status:todo` ラベルを付与する。
4. `dispatch: "immediate"` の場合、対象プロジェクトが実行中でなければ即時ディスパッチ、実行中ならキューに追加する（ラベルは `status:in-progress` に更新）。`dispatch: "queued"` の場合はここで終了する。
5. 上記が成功した直後、レスポンスを返す前に[2-2「指示出し操作直後の同期更新」](#2-2-データ取得仕様ポーリング)の通り`poll_once`を同期実行し、`GET /api/state`が返すキャッシュを最新化する（issue #70）。
6. 処理結果をダッシュボードのレスポンスとして返す。ダッシュボード側はこのレスポンス到達後に`GET /api/state`を再取得し、UIのプロジェクト状況に新規タスク作成を反映する。

## 6. 権限・セキュリティ設計

### 6-1. Agent Runnerのサンドボックス・権限設定

- `claude -p` 起動時に `--dangerously-skip-permissions` フラグを付与し、worktreeディレクトリ内でのフル自動実行を許可する（[アーキテクチャ設計書 7章](./architecture.md#7-権限管理安全対策)）。
- 設定ファイル（`.claude/settings.json`）による権限モード指定は行わず、起動コマンドを見れば挙動が一目瞭然になるようにする。

### 6-2. ネットワークアクセスの認証設計

- アプリケーションレベルの追加認証（Basic認証等）は設けない。
- **MVPでは同一LAN内からのアクセスのみ**を前提とする。ダッシュボード（Next.js）の待受プロセスは、0.0.0.0ではなく**LANインターフェースのIPにのみbind**する（`next dev`/`next start` の `--hostname <lan-ip>` オプション。`npm run dev:lan`/`npm run start:lan`、環境変数 `LAN_IP` に自機のLAN IPを設定して使う）。これにより、同一LANの外からは到達不能にする。
- オーケストレータの内部API（`GET /api/state` 等）は、ダッシュボードのRoute Handlerが**同一マシン上でサーバーサイドから**呼び出す構成（[2-2](#2-2-データ取得仕様ポーリング)参照。ブラウザから直接呼び出すことはない）のため、ネットワークインターフェースに公開する必要が無い。オーケストレータの待受プロセスは`127.0.0.1`（ループバック）にのみbindしたままとする。
- **将来拡張**: 外出先からのアクセスに対応する際は、ダッシュボードのbind先をTailscaleインターフェースIPに切り替える（`--hostname <tailscale-ip>`、`npm run dev:tailscale`/`npm run start:tailscale`）。別issue（#29）で対応する（[要件定義書 4-2](./requirements.md#4-2-将来拡張とする範囲)参照）。

## 7. 配布パッケージ化設計

対応issue: [#110](https://github.com/nosetech/producer-desk/issues/110)

git cloneに依存せず、必要なファイルだけを配布し好きなディレクトリに展開して実行できるようにする。Dockerを使わないMVP方針・Homebrew/pipネイティブ構成という確定済み設計判断（[アーキテクチャ設計書](./architecture.md)）と整合する形で、**GitHub Releasesへのtarball添付**を採用する。

### 配布物の構成

- **dashboard**: `next.config.ts`の`output: "standalone"`でビルドし、`.next/standalone`（`server.js`＋最小限のnode_modulesサブセット）に`.next/static`・`public/`を同梱する。配布先では`npm install`不要、`node server.js`のみで起動できる
- **orchestrator**: `python -m build --wheel`で生成したwheelを配布する。依存が`PyYAML`のみのため、配布先では`pip install <wheel>`のみで済む
- リポジトリ直下の`dist/`ディレクトリに、配布レイアウト専用の`bin/start.sh`・`bin/stop.sh`・`config/projects.yaml.example`・`.env.example`（`SLACK_WEBHOOK_URL`・`ORCHESTRATOR_PORT`・`ORCHESTRATOR_URL`・`DASHBOARD_PORT`・`LAN_IP`。展開先ルートに`.env`を作成すると`bin/start.sh`が起動時に読み込む）・`scripts/`（`backup_usage_db.sh`・launchd plistサンプル）・`SETUP.md`（エンドユーザー向けセットアップ手順書）を用意する。開発用の`bin/start.sh`（git clone・`npm ci`・editable install前提、`orchestrator/.env`・`dashboard/.env`に分かれている）とは別物で、tarball展開後のディレクトリレイアウト（`dashboard/server.js`・`orchestrator/dist/*.whl`が展開先直下に並ぶ構成）に合わせて起動ロジックを書き換え、`.env`もルート直下の単一ファイルに統合している。dashboardのサーバーサイドAPIプロキシ（`dashboard/src/lib/orchestrator.ts`）が接続先として参照する`ORCHESTRATOR_URL`は、`.env`で明示指定しない限り両`bin/start.sh`が`ORCHESTRATOR_PORT`確定後に`http://127.0.0.1:${ORCHESTRATOR_PORT}`として自動導出・exportする（issue #137）
- `docs/`・`CLAUDE.md`・`.claude/`・`tests/`・`.github/`はproducer-deskを**開発する**ための資材のため配布物に含めない

### `orchestrator`のインストール形態非依存化

`orchestrator/orchestrator/config.py`の`REPO_ROOT`は、従来`Path(__file__).resolve().parents[2]`（ソースツリー上のファイル位置からの逆算）で決定していた。これはeditable install（`pip install -e .`、開発時のgit clone運用）でのみ正しく動作し、wheelインストールではパッケージが`site-packages/orchestrator/`直下にフラットに配置されるため誤ったパスを指してしまう。`orchestrator/pyproject.toml`の有無でインストール形態を判定し、wheelインストール時はカレントディレクトリ（配布物のルートディレクトリで起動する前提）にフォールバックするよう変更した（`_detect_repo_root()`）。`config/projects.yaml`・`config/sessions.json`・`config/usage.db`・`logs/`のデフォルトパスは全てこの`REPO_ROOT`を起点にしているため、この修正により配布先でも`dist/bin/start.sh`が展開先ルートで`orchestrator`コマンドを実行するだけで正しく動作する。

### `.github/workflows/release.yml`

セマンティックバージョンタグ（`v*.*.*`）のpushでのみ起動する（`pull_request`・`workflow_dispatch`トリガーは持たない）。タグのバージョンと`orchestrator/pyproject.toml`・`dashboard/package.json`の`version`が一致することを検証する`validate-version`ジョブを経て、`dashboard`・`orchestrator`それぞれで既存CI（`dashboard-ci.yml`/`orchestrator-ci.yml`）相当のformat/lint/test/typecheckを再実行した上でビルドし、`package-and-release`ジョブが`dist/`の内容とビルド成果物を1つのtarball（`producer-desk-<version>.tar.gz`）にまとめて`gh release create --generate-notes`でアセット添付する。同一タグへのリリース再実行は非対応（タグ・リリースの手動削除が必要）。

### リリース準備（`.claude/skills/release-prepare`）

タグを打つ前段として、バージョン番号の確定（`orchestrator/pyproject.toml`・`dashboard/package.json`の`version`更新）と`develop`→`master`のプルリクエスト作成を補助するSKILL。**`master`へのマージ・タグ付け（`git tag vX.Y.Z` → push）は人間が最終承認した上で行い、本SKILLの範囲では実施しない**（`master`への直接コミット禁止というブランチ運用ルールと整合させるため、あくまでPR経由の変更に限定する）。マージ後、`master`上のマージコミットにタグを打つことで`release.yml`が起動する。

### 前提・注意点

- Node.js／Python 3.11以降／`gh` CLI／Claude Code CLI（サブスクリプション認証）は引き続きOS側の前提としてユーザー自身にインストールしてもらう（Docker不使用の方針上、tarballに同梱できない）
- Homebrew formula化も選択肢にあるが、公開tap運用のオーバーヘッドに見合うほどの配布規模（不特定多数への公開）ではないため、まずはGitHub Releasesのtarballで十分と判断した

## 成果物

- 本書（データモデル定義、状態遷移フロー、API仕様、Agent Runner連携仕様、通知フロー、権限設計、配布パッケージ化設計）
- [design-prompt-dashboard.md](./design-prompt-dashboard.md)（Claude Designへの画面設計委譲プロンプト）

## 参考

- [要件定義書](./requirements.md)
- [アーキテクチャ設計書](./architecture.md)
- [poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md)

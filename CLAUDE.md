# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## リポジトリの現状

`producer-desk` は、自走型AI開発オーケストレーションシステムの**設計フェーズのドキュメントリポジトリ**である。現時点でアプリケーションコードは存在せず、`docs/` 以下のMarkdown設計文書のみで構成されている。そのためビルド・lint・テストの類のコマンドは存在しない。実装フェーズは別途管理される想定（`docs/requirements.md` 冒頭の親issue参照）。

## ドキュメント構成と読む順序

各ドキュメントは前段の内容を前提として積み上がっているため、以下の順に読むこと。

1. `docs/requirements.md` — 要件定義（issue #2）。想定ユーザー（プロデューサー1名、並行3〜5プロジェクト）、機能/非機能要件、MVPスコープ
2. `docs/architecture.md` — アーキテクチャ設計（issue #3）。全体構成図、コンポーネント間通信方式、エージェント実行基盤の方針
3. `docs/basic-design.md` — 基本設計（issue #4）。ラベルによる状態遷移の詳細、内部API仕様、Agent Runner起動仕様、通知フロー、権限設計
4. `docs/design-prompt-dashboard.md` / `docs/design-prompt-dashboard-diff*.md` — ダッシュボードの画面設計を別セッションのClaude（Claude Design）に委譲するための、そのままコピペして使うプロンプト。`-diff*` の方は初回デザイン後の差分追加依頼用で、単独では使わない。画面はダッシュボードとプロジェクト別issue一覧の2つ（サイドバーで切替、issue #116）

各ドキュメントは相互にMarkdownリンク・見出しアンカーで参照し合っている。一方を編集した際は、他方からの参照（アンカー文字列を含む）が壊れていないか確認すること。

## 画面デザインの実装ルール

ダッシュボードの画面実装は、Claude Designで作成された以下のデザインを**正**として忠実に実装すること。レイアウト・配色・コンポーネント構成・インタラクションを独自解釈で変更しない。

- デザイン: https://claude.ai/design/p/d67961c7-d882-4efb-bac8-492338ae41c4?file=ProducerDesk.dc.html

このデザインは `docs/design-prompt-dashboard.md` / `docs/design-prompt-dashboard-diff.md` のプロンプトを元に作成されたもの。デザインとdocs側の仕様（表示項目・API仕様等）に齟齬がある場合は、実装前にどちらを正とするか確認すること。デザインが更新された場合は、この節のURLも合わせて更新する。

**重要**: 上記URLは `claude.ai` の認証が必要なページであり、`WebFetch` 等の非対話的な取得では403になり中身を見られない（配色・アイコンの指定はこのURLの実際のレンダリング結果にしかなく、docs側のテキストには書かれていない）。

**実装・レビュー時は必ず `DesignSync` MCPツールでこのデザインの実ソース（`ProducerDesk.dc.html`）を直接取得し（`ProducerDesk.dc.html`はテンプレート、スタイル・状態ロジックは`ProducerDesk.logic.js`に分割されているため**両方**を取得する）、実際のCSS/JS値（色・余白・border-radius・アニメーション等）を確認してから実装すること。** 手順は以下の通り（`projectId` はURLの `/p/<uuid>` 部分、`d67961c7-d882-4efb-bac8-492338ae41c4`）。

1. `DesignSync` の `get_project` で `projectId` が読めることを確認する（`list_projects` はデザインシステム種別のプロジェクトのみを返すため、このプロジェクト（`type: PROJECT_TYPE_PROJECT`）は一覧に出てこない。`get_project`/`list_files`/`get_file` は `projectId` を直接渡せば種別を問わず使える）
2. `list_files` で対象ファイル一覧（`ProducerDesk.dc.html`・`ProducerDesk.logic.js` 等）を確認する
3. `get_file` でファイルの中身をそのまま取得する（256KiB上限）。対象コンポーネントに対応するスタイルオブジェクト定義（例: `confirmDialogStyle`、`approveBtn`、`diagBtnStyle` 等。主に`ProducerDesk.logic.js`側にある）をそのテキストから直接読み取り、値をそのまま実装に反映する
4. **レスポンスの`truncated`を必ず確認する。** `truncated: true`の場合は末尾が欠けており、スタイル定義を取りこぼしている可能性がある（issue #219で`ProducerDesk.dc.html`が256KiBを超えて切れ、ボタンのスタイルが取得できず実装が既存ボタンの見た目の流用になった）。`true`のときは取得できた範囲だけで実装を進めず（既存コンポーネントの見た目を流用して代替するのも不可）、その旨を明記して作業を停止し、Claude Design側でのファイル分割を人間に依頼すること

`DesignSync` の利用には、`claude.ai` ログインへのデザインシステムアクセス権限が必要。**この権限は一度 `/design-login`（ローカルコマンド、または通常の `claude.ai` ログインでのデザインアクセス許可）を実行すればmacOSキーチェーン（サービス名 `Claude Code-credentials`）に永続化され、同一ホスト・同一OSユーザーで動く以降の `claude` CLI呼び出し（Agent Runnerの `claude -p` を含む）から自動的に利用できる。** そのためAgent Runner自身が実行時に認証フローを行う必要はない（運用開始前にホスト上で一度だけ人間が `/design-login` を実行しておけば足りる。詳細は `docs/basic-design.md` 3-1参照）。

**このURLをブラウザ操作ツール（`mcp__claude-in-chrome__*`）で開いてキャンバス上の要素をクリックしてコードを選択したり、プレビューをズームしたスクリーンショットから目視でCSS値を推測したりするのは絶対に行わないこと。** プレビューは静的なスナップショットで状態を持つインタラクション（ダイアログ表示等）が再現されず、キャンバス上の要素クリックによるコード選択も自動操作からは機能しないことが確認済み（producer-desk PR #57）。目視推測も丸め誤差や見落としが起きやすく、不正確な値のまま実装を進めるくらいなら停止すべきである。

**`DesignSync` が権限不足等で使えない場合はフォールバックせず、その旨を明記してそこで作業を停止し、人間の確認を仰ぐこと。** ブラウザ操作ツールでの代替取得（チャットへの問い合わせ等）は不正確になりうるため、`DesignSync` の代わりとして使わない。

`DesignSync` で値を取得できた場合、実装後はブラウザ操作ツールで完成品とデザインのプレビューを並べて**最終的な見た目の一致を確認する**（気づいていない要素の見落とし確認等。これは数値の取得手段ではなく完成後のセルフレビュー用途）。

Agent Runner実行時もworktreeのこの`CLAUDE.md`が読み込まれるため、上記の指示はそのまま適用される（プロジェクトごとの指示であり、Agent Runner共通の`--append-system-prompt`では付与しない。`docs/basic-design.md` 3-6参照）。

### UI変更のスクリーンショット・動画をissueに添付する場合（issue #218）

レビュー用に実装結果の見た目をissueコメントへ添付するときの手順。プロンプト設定の`attachment_instruction`と同じ内容で、仕様は`docs/basic-design.md` 2-4参照。

- `gh issue comment <n> --attach <file>`で添付する（`gh` v2.99.0以上）。画像・動画のみ、サイズ上限は10MB
- 静止画で足りる場合はスクリーンショットにする。動画はアニメーション・ホバー・状態遷移など動きを見せないと判断できない場合に限り、Playwrightの`recordVideo`（`.webm`）のみで録画する（Playwright専用ffmpeg: `npx playwright-core install ffmpeg`）
- 確認用ダッシュボードは上記のとおり本番と衝突しない別ポートで起動する
- 録画・撮影は、承認・返信・新規作成・保存などの書き込み系ボタンを押さず、読み取り専用の操作のみで行う。秘匿情報が映り込んでいないことを確認してから添付する

## 確定済みの設計判断（変更時は要注意）

以下はプロデューサーとの対話で確定し、複数ドキュメントに横断的に反映されている前提。ドキュメントを更新する際、これらと矛盾する記述を残さないよう注意する。

- 利用者はプロデューサー1名のみ。複数ユーザー対応・権限分離はMVPで考慮しない
- **GitHub Issues/Projectsが正のデータストア**。独自DBは持たない。状態は単一の排他的ラベルで表現する: `status:todo` → `status:in-progress` → `needs-human-decision` → `status:in-review` → `status:closed`（issueクローズをオーケストレータがポーリングで検知し自己付与。`docs/basic-design.md` 1章参照）。この5つの状態ラベルのいずれも付与されていないissueはproducer-deskの管理対象外として扱い、ダッシュボードの判断待ち一覧・最近の活動には表示しない
- ラベル操作は**冪等**に行う（`gh` のadd/remove-labelは非atomicなため、現在のラベルを取得してから差分のみ適用する。`basic-design.md` 1章の擬似コード参照）
- Agent Runnerは常駐プロセスではなく **`claude -p ... --resume ... --dangerously-skip-permissions` のワンショット実行**（worktreeディレクトリはCLIフラグではなくsubprocessの`cwd`引数で指定する。実CLIに`--cwd`フラグは存在しないため、`basic-design.md` 3-1参照）。プロジェクトごとにgit worktreeで隔離し、同一プロジェクトへの同時実行は行わずFIFOキューで順次処理する
- 自走タスク本体を含め、**実行手段をプロジェクトごとにユーザーが選択可能**とする（issue #148/#174で確定、従来の「自走タスク本体はClaude Codeのみ」という制限は撤廃）。(A) Claude Code CLI直利用＋**Claude Code Pro/Maxプラン等のサブスクリプション**、または (B) **LiteLLM Proxy経由**（Docker不使用のネイティブ構成、`ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`で接続先切替）で他社プロバイダ・ローカルLLMを従量課金で利用、のいずれかを選べる。既存のAgent Runner起動方式（`claude -p`ワンショット・worktree隔離）は作り替えない。(A)選択時、利用リミット到達時は追加コストを払わずリセットまで待機する（詳細は`architecture.md` 5章、`basic-design.md` 4章参照）
- MVPでは**Dockerを使わずネイティブ構成**（Homebrew/pip等）。PoC環境でDockerのネットワーク操作がハングする問題が確認されたため
- コンポーネント間通信は**ポーリングに統一**（Webhookは不採用）。ローカルネットワーク内で完結させる前提のため、外部到達可能なエンドポイントを必要とする方式は避ける
- ネットワーク・認証は**MVPでは同一LAN内アクセスのみ**で保護し、アプリレベルの追加認証（Basic認証等）は設けない。**Tailscale経由での外出先アクセスは環境変数`TAILSCALE_IP`でdashboardのbind先を切り替えて対応済み（issue #29、`LAN_IP`との同時指定は不可）**（`requirements.md` 4-2、`architecture.md` 8章、`basic-design.md` 6-2参照）
- 通知は**Slack Incoming Webhook**（一方向）。Claude Code純正のChannelsプラグイン（Telegram/Discord/iMessage）は使わない
- AIへの指示出しは**GitHub issueコメント経由**（案A）。ダッシュボードのボタン操作・自由記述テキストボックスも、内部的にはissueコメント投稿として実装する。専用API（案B）は将来拡張

## 開発ワークフロー（`.claude/skills/fix-github-issue` 参照）

- ブランチ運用: `master`（安定版） → `develop`（結合） → `feature/*`（作業ブランチ、`develop`から切る）
- 変更は必ずPRで`develop`に取り込む。GitHub issueに対応する変更は、PR本文に `Closes #<issue番号>` を記載する
- issueはこのシステムの設計フェーズの進行管理に使われている（要件定義 #2 → アーキテクチャ設計 #3 → 基本設計 #4 の順）。各ドキュメント冒頭に対応issue番号が記載されている
- 前提となる調査資料は別リポジトリ `nosetech/research-log` の `log/2026/07/autonomous-dev-orchestration/` 配下にあり、各ドキュメントからリンクされている（`existing-tools.md` / `architecture-and-challenges.md` / `poc-results.md`）
- PR作成時は `.github/workflows/` のCIでフォーマット・lint・テストが自動実行される（`orchestrator/**` / `dashboard/**` の変更パスに応じてジョブが分岐）。push前にローカルで以下を実行し、CI落ちを防ぐこと
  - `orchestrator/`: `ruff format .` → `ruff check .` → `pytest`（事前に `pip install -e ".[dev]"`）
  - `dashboard/`: `npm run format` → `npm run lint` → `npx tsc --noEmit`

### Agent Runner自身が動作確認のためオーケストレータ・ダッシュボードを起動する場合

Agent Runner（worktree内で作業しているClaude Code自身）が自分の変更を確認する目的でオーケストレータやダッシュボードを起動・停止する際は、**必ず `./bin/dev_instance.sh start` / `./bin/dev_instance.sh stop` を使うこと**（`status`で状態確認も可能。issue #238）。

- `start`は、空きポート（18000番台）の自動採番、dashboardの`ORCHESTRATOR_URL`の自動調整、`PROJECTS_CONFIG_PATH`・`SESSIONS_PATH`等の開発用ファイル（`.dev-run/`配下）への切替、起動したプロセスグループの記録（`.dev-run/`）を行う。既定ポート（8787/3000）の指定や使用中ポートは拒否される（`DEV_ORCHESTRATOR_PORT` / `DEV_DASHBOARD_PORT`で明示指定も可能）。起動後に標準出力されるURLで動作確認する
- `stop`は、記録したプロセスグループ（PID・PGID・起動時に付与した目印）が一致する場合だけ停止する。名前・ポートからの検索はしない
- **`pkill` / `killall` / `lsof`・`netstat`でポートからPIDを探してのkillなど、名前やポートでプロセスを探して止める操作は禁止する。** 運用インスタンスや他worktreeのインスタンスは`ps`上でほぼ同じ見た目（`python -m orchestrator.main` / `next-server`）で区別できず、巻き込んで運用中のプロセスを止めてしまうため
- **確認用インスタンスは常に読み取り専用モード（`ORCHESTRATOR_READ_ONLY=1`）で、`nosetech/producer-desk`を対象に起動する**（issue #241）。実issueに対するディスパッチ・ラベル変更・コメント投稿・Slack通知は一切行わず、書き込み系API・ボタン操作は失敗する（撮影・確認は読み取り専用の操作のみ）。見た目確認用の固定issue #242（`status:in-review`）が表示される。クローズ・編集・コメント追加はしない
- dashboardもorchestratorと同じ環境変数`PROJECTS_CONFIG_PATH`（設定があれば`LITELLM_CONFIG_PATH`も）で設定ファイルを読む（issue #244）。**確認用ダッシュボードのために`config/projects.yaml`等を直接置いたり書き換えたりしない**（運用側のファイルを触らないため）。`dev_instance.sh`が`.dev-run/projects.yaml`を渡す
- 運用インスタンス由来の`NODE_ENV=production`のままだと`next dev`が500になるため、`dev_instance.sh`は`NODE_ENV`を外して起動し、起動後にHTTP 200でなければ警告する。手動で`next dev`を起動する場合も`NODE_ENV`を外すこと
- 画面の見た目を確認できなかった場合は、PRコメント・最終応答にその原因を明記する（確認できたと書かない）
- シェルには運用インスタンス由来の`ORCHESTRATOR_PORT=8787`等が継承されていることがあるが、`dev_instance.sh`はこれらを参照せず、子プロセスには採番した値で上書きして渡す

以下の手動起動例は、`dev_instance.sh`が内部で行っている動作の説明であり、代替手段ではない（手動起動すると止め方を誤りやすいため使わない）。

- オーケストレータ: 環境変数 `ORCHESTRATOR_PORT` でポートを上書きする（例: `ORCHESTRATOR_PORT=8788 python -m orchestrator.main`）
- ダッシュボード: `next dev`/`next start` の `-p <port>` オプションでポートを上書きし、`ORCHESTRATOR_URL` 環境変数も確認用オーケストレータのポートに合わせる（例: `ORCHESTRATOR_URL=http://127.0.0.1:8788 npm run dev -- -p 3001`）

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## リポジトリの現状

`producer-desk` は、自走型AI開発オーケストレーションシステムの**設計フェーズのドキュメントリポジトリ**である。現時点でアプリケーションコードは存在せず、`docs/` 以下のMarkdown設計文書のみで構成されている。そのためビルド・lint・テストの類のコマンドは存在しない。実装フェーズは別途管理される想定（`docs/requirements.md` 冒頭の親issue参照）。

## ドキュメント構成と読む順序

各ドキュメントは前段の内容を前提として積み上がっているため、以下の順に読むこと。

1. `docs/requirements.md` — 要件定義（issue #2）。想定ユーザー（プロデューサー1名、並行3〜5プロジェクト）、機能/非機能要件、MVPスコープ
2. `docs/architecture.md` — アーキテクチャ設計（issue #3）。全体構成図、コンポーネント間通信方式、エージェント実行基盤の方針
3. `docs/basic-design.md` — 基本設計（issue #4）。ラベルによる状態遷移の詳細、内部API仕様、Agent Runner起動仕様、通知フロー、権限設計
4. `docs/design-prompt-dashboard.md` / `docs/design-prompt-dashboard-diff.md` — ダッシュボードの画面設計を別セッションのClaude（Claude Design）に委譲するための、そのままコピペして使うプロンプト。`-diff` の方は初回デザイン後の差分追加依頼用で、単独では使わない

各ドキュメントは相互にMarkdownリンク・見出しアンカーで参照し合っている。一方を編集した際は、他方からの参照（アンカー文字列を含む）が壊れていないか確認すること。

## 画面デザインの実装ルール

ダッシュボードの画面実装は、Claude Designで作成された以下のデザインを**正**として忠実に実装すること。レイアウト・配色・コンポーネント構成・インタラクションを独自解釈で変更しない。

- デザイン: https://claude.ai/design/p/d67961c7-d882-4efb-bac8-492338ae41c4?file=ProducerDesk.dc.html

このデザインは `docs/design-prompt-dashboard.md` / `docs/design-prompt-dashboard-diff.md` のプロンプトを元に作成されたもの。デザインとdocs側の仕様（表示項目・API仕様等）に齟齬がある場合は、実装前にどちらを正とするか確認すること。デザインが更新された場合は、この節のURLも合わせて更新する。

**重要**: 上記URLは `claude.ai` の認証が必要なページであり、`WebFetch` 等の非対話的な取得では403になり中身を見られない（配色・アイコンの指定はこのURLの実際のレンダリング結果にしかなく、docs側のテキストには書かれていない）。

**実装・レビュー時は必ず `DesignSync` MCPツールでこのデザインの実ソース（`ProducerDesk.dc.html`）を直接取得し、実際のCSS/JS値（色・余白・border-radius・アニメーション等）を確認してから実装すること。** 手順は以下の通り（`projectId` はURLの `/p/<uuid>` 部分、`d67961c7-d882-4efb-bac8-492338ae41c4`）。

1. `DesignSync` の `get_project` で `projectId` が読めることを確認する（`list_projects` はデザインシステム種別のプロジェクトのみを返すため、このプロジェクト（`type: PROJECT_TYPE_PROJECT`）は一覧に出てこない。`get_project`/`list_files`/`get_file` は `projectId` を直接渡せば種別を問わず使える）
2. `list_files` で対象ファイル一覧（`ProducerDesk.dc.html` 等）を確認する
3. `get_file` でファイルの中身をそのまま取得する（256KiB上限、ページ全体が1ファイルなのでほぼこれで足りる）。対象コンポーネントに対応するスタイルオブジェクト定義（例: `confirmDialogStyle`、`approveBtn` 等）をそのテキストから直接読み取り、値をそのまま実装に反映する

`DesignSync` の利用には、`claude.ai` ログインへのデザインシステムアクセス権限が必要。付与済みでない場合は、ユーザーに `/design-login`（ローカルコマンド）の実行を依頼すること。

**このURLをブラウザ操作ツール（`mcp__claude-in-chrome__*`）で開いてキャンバス上の要素をクリックしてコードを選択したり、プレビューをズームしたスクリーンショットから目視でCSS値を推測したりするのは避けること。** プレビューは静的なスナップショットで状態を持つインタラクション（ダイアログ表示等）が再現されず、キャンバス上の要素クリックによるコード選択も自動操作からは機能しないことが確認済み（producer-desk PR #57）。目視推測も丸め誤差や見落としが起きやすい。

`DesignSync` が権限不足等で使えない場合のフォールバックは以下の優先順で行う。

1. ブラウザ操作ツールでデザインのチャット欄を開き、「変更せず、生のソースコードをそのまま出力して」と対象コンポーネントのスタイル定義を明示的に指定して依頼する（要約させると細部が欠落する。producer-desk PR #57でこの方法自体は機能することを確認済み）
2. それも使えない場合は、その旨を実行結果コメントに明記し `needs-human-decision` として人間の確認を仰ぐ

いずれの方法で値を取得した場合も、実装後はブラウザ操作ツールで完成品とデザインのプレビューを並べて**最終的な見た目の一致を確認する**（気づいていない要素の見落とし確認等）。

Agent Runner実行時も同様の指示を `--append-system-prompt` で毎回付与している（`orchestrator/orchestrator/agent_runner.py` の `AGENT_RUNNER_DESIGN_VERIFICATION_INSTRUCTION`、`docs/basic-design.md` 3-1参照）。

## 確定済みの設計判断（変更時は要注意）

以下はプロデューサーとの対話で確定し、複数ドキュメントに横断的に反映されている前提。ドキュメントを更新する際、これらと矛盾する記述を残さないよう注意する。

- 利用者はプロデューサー1名のみ。複数ユーザー対応・権限分離はMVPで考慮しない
- **GitHub Issues/Projectsが正のデータストア**。独自DBは持たない。状態は単一の排他的ラベルで表現する: `status:todo` → `status:in-progress` → `needs-human-decision` → `status:in-review` → `status:closed`（issueクローズをオーケストレータがポーリングで検知し自己付与。`docs/basic-design.md` 1章参照）。この5つの状態ラベルのいずれも付与されていないissueはproducer-deskの管理対象外として扱い、ダッシュボードの判断待ち一覧・最近の活動には表示しない
- ラベル操作は**冪等**に行う（`gh` のadd/remove-labelは非atomicなため、現在のラベルを取得してから差分のみ適用する。`basic-design.md` 1章の擬似コード参照）
- Agent Runnerは常駐プロセスではなく **`claude -p ... --resume ... --dangerously-skip-permissions` のワンショット実行**（worktreeディレクトリはCLIフラグではなくsubprocessの`cwd`引数で指定する。実CLIに`--cwd`フラグは存在しないため、`basic-design.md` 3-1参照）。プロジェクトごとにgit worktreeで隔離し、同一プロジェクトへの同時実行は行わずFIFOキューで順次処理する
- MVPでは **LiteLLM Proxy等のモデルルーターを導入しない**。Claude Code CLIを直接利用し、Anthropic APIの従量課金ではなく**Claude Code Pro/Maxプラン等のサブスクリプション**を使う。利用リミット到達時は追加コストを払わずリセットまで待機する
- MVPでは**Dockerを使わずネイティブ構成**（Homebrew/pip等）。PoC環境でDockerのネットワーク操作がハングする問題が確認されたため
- コンポーネント間通信は**ポーリングに統一**（Webhookは不採用）。ローカルネットワーク内で完結させる前提のため、外部到達可能なエンドポイントを必要とする方式は避ける
- ネットワーク・認証は**MVPでは同一LAN内アクセスのみ**で保護し、アプリレベルの追加認証（Basic認証等）は設けない。**Tailscale経由での外出先アクセス対応は別issueの将来拡張**とする（`requirements.md` 4-2、`architecture.md` 8章、`basic-design.md` 6-2参照）
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

Agent Runner（worktree内で作業しているClaude Code自身）が自分の変更を確認する目的でオーケストレータやダッシュボードを起動する際、**本番用に既に起動済みのインスタンスとポートが衝突しないよう、必ず別ポートで起動すること**。デフォルトポート（オーケストレータ8787・ダッシュボード3000）で起動すると、既存プロセスがいる場合に起動失敗、または意図せず同一プロセスに繋がってしまう。

- オーケストレータ: 環境変数 `ORCHESTRATOR_PORT` で上書きする（例: `ORCHESTRATOR_PORT=8788 python -m orchestrator.main`）
- ダッシュボード: `next dev`/`next start` の `-p <port>` オプションで上書きする（例: `npm run dev -- -p 3001`）。この確認用ダッシュボードから確認用オーケストレータを参照させる場合は、`ORCHESTRATOR_URL` 環境変数もポートを合わせて設定する（例: `ORCHESTRATOR_URL=http://127.0.0.1:8788 npm run dev -- -p 3001`）

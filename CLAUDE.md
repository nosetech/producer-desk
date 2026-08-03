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

## 確定済みの設計判断（変更時は要注意）

以下はプロデューサーとの対話で確定し、複数ドキュメントに横断的に反映されている前提。ドキュメントを更新する際、これらと矛盾する記述を残さないよう注意する。

- 利用者はプロデューサー1名のみ。複数ユーザー対応・権限分離はMVPで考慮しない
- **GitHub Issues/Projectsが正のデータストア**。独自DBは持たない。状態は単一の排他的ラベルで表現する: `status:todo` → `status:in-progress` → `needs-human-decision` → `status:in-review` → （issueクローズ＝完了）
- ラベル操作は**冪等**に行う（`gh` のadd/remove-labelは非atomicなため、現在のラベルを取得してから差分のみ適用する。`basic-design.md` 1章の擬似コード参照）
- Agent Runnerは常駐プロセスではなく **`claude -p ... --resume ... --cwd ... --dangerously-skip-permissions` のワンショット実行**。プロジェクトごとにgit worktreeで隔離し、同一プロジェクトへの同時実行は行わずFIFOキューで順次処理する
- MVPでは **LiteLLM Proxy等のモデルルーターを導入しない**。Claude Code CLIを直接利用し、Anthropic APIの従量課金ではなく**Claude Code Pro/Maxプラン等のサブスクリプション**を使う。利用リミット到達時は追加コストを払わずリセットまで待機する
- MVPでは**Dockerを使わずネイティブ構成**（Homebrew/pip等）。PoC環境でDockerのネットワーク操作がハングする問題が確認されたため
- コンポーネント間通信は**ポーリングに統一**（Webhookは不採用）。Tailscaleの閉域網内で完結させる前提のため、外部到達可能なエンドポイントを必要とする方式は避ける
- ネットワーク・認証は**Tailscaleのネットワーク境界のみ**で保護し、アプリレベルの追加認証（Basic認証等）は設けない
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

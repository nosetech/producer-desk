# 要件定義書: 自走型AI開発オーケストレーションシステム（producer-desk）

- 対応issue: [#2](https://github.com/nosetech/producer-desk/issues/2)（親issue: [#1](https://github.com/nosetech/producer-desk/issues/1)）
- 作成日: 2026-08-03
- 前提となる調査: `nosetech/research-log` リポジトリ [`log/2026/07/autonomous-dev-orchestration/`](https://github.com/nosetech/research-log/tree/main/log/2026/07/autonomous-dev-orchestration) 配下
  - `existing-tools.md`（issue #63） / `architecture-and-challenges.md`（issue #64） / `poc-results.md`（issue #65）

## 1. 利用者・利用シーン

- **想定ユーザー数**: 1名（プロデューサー本人のみ）。複数ユーザー対応は対象外。
- **想定並行プロジェクト数**: 3〜5プロジェクト程度を目安とする。
- **主な利用シーン**:
  1. 就寝前後、同一Wi-Fi内での状況確認（各プロジェクトの判断待ち・進捗をまとめて確認し、翌日の方針を指示する）
  2. PC前での集中レビュー（デスクトップでダッシュボードを開き、複数プロジェクトをまとめてレビュー・指示する）
  - 外出先からのVPN経由アクセスや、通知駆動での即時対応は上記2シーンに比べて優先度を下げる（[2-6](#2-6-通知)参照）。

## 2. 機能要件

### 2-1. ダッシュボード表示項目

- 判断待ち一覧（`needs-human-decision` ラベルが付与されたissueの横断集約）
- 最近の活動ログ（タイムライン形式。Agent Runnerの直近のコミット・PR・issue更新）
- コスト（API利用量）モニター（[3-4](#3-4-コスト制約)の月額上限と連動）
- プロジェクト別サマリは今回のMVPでは対象外とする。

### 2-2. 「判断が必要な項目」の判定規約

- `needs-human-decision` ラベルの有無のみで判定する。
- 担当者(assignee)の有無による判定は、PoC（[poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md) 1章）で識別力が無いことが確認済みのため採用しない。
- エージェントが「人間の判断が必要」と自ら判断したタイミングで能動的にラベルを付与する運用規約とする。

### 2-3. AIへの指示出し導線

- 案A（GitHub issueコメント経由）でMVPを開始する。
  - ダッシュボード上のワンタップ操作（[2-7](#2-7-承認却下操作)）は、内部的にissueへのコメント投稿として実装する。
  - オーケストレータ役のポーリングスクリプトが新規コメントを検知し、Agent Runnerへディスパッチする（[poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md) PoC-A参照）。
- 専用API経由（案B）は将来拡張とする。レイテンシは低いが実装コストが高いため、MVPのスコープには含めない。

### 2-4. Agent Runnerの起動・停止・プロジェクト追加時の運用フロー

- MVPでは、CLIコマンドによる手動起動・停止とする。
- プロジェクト追加時も、プロデューサーが手動でRunnerを起動する運用とする。
- オーケストレータによる自動起動・停止・スケーリングは将来拡張とする。

### 2-5. モデル選択方針

- MVPではClaudeのみを利用する。
  - ローカルLLMはツール呼び出し（Function Calling）の信頼性がモデルサイズに強く依存し不安定であることがPoC（[architecture-and-challenges.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/architecture-and-challenges.md) 2-4節）で確認されているため、コード変更を伴う自走タスクには現時点で採用しない。
- ただし、Agent RunnerからはLiteLLM Proxy経由でモデルを呼ぶ構成にしておき、将来的なローカルLLM併用（設定ファイルの変更のみでの切り替え）に備える。

### 2-6. 通知要件

- Claude Code Remote ControlのPush通知は実機検証（Android、3回）で一度も届かず、信頼性に課題があることが判明している（[poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md) 7-1節）。
- Telegram等の公式Channelsプラグインを併用し、Push通知の信頼性をプラットフォーム側に委ねる形で補完する。
- 主な利用シーンが「就寝前後」「PC前レビュー」中心で即時性の優先度が低いことも踏まえ、Push通知の到達を前提にしすぎない設計とする。

### 2-7. 承認・却下操作の要件

- ダッシュボード上でワンタップでの承認・却下操作を提供する（[2-3](#2-3-aiへの指示出し導線)の通り、内部的にはissueコメント投稿として実装）。

## 3. 非機能要件

### 3-1. セキュリティ・認証

- Tailscaleによるネットワーク境界のみで保護し、アプリケーションレベルの追加認証（Basic認証等）は設けない。
- 同一Wi-Fi内・外出先を問わず、Tailscaleの同一ネットワーク経由でのみダッシュボードにアクセス可能な構成とする。

### 3-2. 権限管理・安全対策

- プロジェクトごとにgit worktreeで隔離し、隔離範囲内では自動実行（`--dangerously-skip-permissions` 相当）を許可する。
- コンテナ（Docker）による隔離は、[4-2](#4-2-対象外とする既存ツールpoc結果の扱い)の理由によりMVPでは採用しない。worktree隔離のみとし、コンテナ隔離は将来拡張とする。

### 3-3. 可用性

- `caffeinate` 等によるPCスリープ防止を運用前提とする。
- ネットワーク切断時は、Claude Code Remote Control標準の自動再接続に依存する。

### 3-4. コスト制約

- Claude APIの月額利用上限を設定する。
- 上限に近づいた場合は通知、超過した場合はAgent Runnerを自動停止する。

### 3-5. 運用体制

- issue #1の前提通り、1人運用（プロデューサー単一）を前提とする。
- 将来的な複数ユーザー対応・権限分離は考慮しない。

## 4. スコープ確定（MVP）

### 4-1. MVPに含める範囲

- ダッシュボード（判断待ち一覧／最近の活動ログ／コストモニター、ワンタップ承認・却下）
- GitHub issueコメント経由の指示出し（案A）
- モデルはClaudeのみ（LiteLLM Proxy経由の構成で将来拡張に備える）
- Tailscaleのネットワーク境界のみによる認証
- プロジェクトごとのgit worktree隔離
- CLIコマンドによるAgent Runnerの手動起動・停止
- Telegram等Channels併用による通知の信頼性補完
- Claude API月額利用上限と自動停止

### 4-2. 将来拡張とする範囲

- ローカルLLMの併用（LiteLLM Proxyによるモデルルーティング）
- 専用API経由の指示出し導線（案B）
- オーケストレータによるAgent Runnerの自動起動・停止・スケーリング
- コンテナ（Docker）によるプロジェクト隔離
- 複数ユーザー対応・権限分離

### 4-3. 対象外とする既存ツール・PoC結果の扱い

- **Docker構成**: PoC環境（[poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md) 2章）でDockerのネットワーク関連操作が恒常的にハングする問題が発生し、Homebrew/pipによるネイティブインストールで回避した経緯がある。本番の実際のPC環境での動作確認は未実施のため、MVPではDockerを使わずネイティブ構成（Homebrew/pip等）を採用する。将来Docker採用を検討する場合は、本番PC環境での事前検証を行う。
- **Tailscale/WireGuard実機セットアップ**: issue #1のスコープ外（ユーザー自身の実機作業）としてPoC側で既に整理済み。本要件定義でもプロデューサー自身の作業として扱う。

## 参考

- [existing-tools.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/existing-tools.md)
- [architecture-and-challenges.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/architecture-and-challenges.md)
- [poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md)

# アーキテクチャ設計書: 自走型AI開発オーケストレーションシステム（producer-desk）

- 対応issue: [#3](https://github.com/nosetech/producer-desk/issues/3)（親issue: [#1](https://github.com/nosetech/producer-desk/issues/1)、前提issue: [#2](https://github.com/nosetech/producer-desk/issues/2)）
- 作成日: 2026-08-03
- 前提: [要件定義書](./requirements.md)
- 前提となる調査: [architecture-and-challenges.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/architecture-and-challenges.md)（issue #64） / [poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md)（issue #65）

## 1. 全体構成

### 構成図

```mermaid
flowchart TB
    subgraph Mobile["モバイル / PC（Tailscale経由）"]
        A["ブラウザ（ダッシュボード）"]
        N["Discord アプリ"]
    end

    subgraph HomeNet["自宅ネットワーク（ローカルPC・Tailscale配下）"]
        B["ダッシュボード Web UI（Next.js）"]
        C["オーケストレータ（ポーリングスクリプト）"]
        D1["Agent Runner: project-a<br/>claude -p（ワンショット、worktree隔離）"]
        D2["Agent Runner: project-b<br/>claude -p（ワンショット、worktree隔離）"]
        D3["Agent Runner: project-c<br/>claude -p（ワンショット、worktree隔離）"]
    end

    H["GitHub Issues（データ層・状態機械）"]
    Discord["Discord（Channels）"]

    A <--> B
    B <--> C
    C -- "ポーリング" --> H
    C -- "検知した指示をディスパッチ" --> D1 & D2 & D3
    D1 & D2 & D3 -- "ラベル更新・コメント投稿" --> H
    C -- "判断待ち発生を通知" --> Discord
    Discord --> N
```

- モデルルーター（LiteLLM Proxy）はMVPでは導入しない（[5章](#5-モデルルーティング)参照）。
- ダッシュボード・Discordともに、モバイル/PCからのアクセスはTailscaleのネットワーク境界のみで保護する（[8章](#8-ネットワーク構成)参照）。

### コンポーネント一覧と責務

| コンポーネント | 責務 | 技術 |
|---|---|---|
| ダッシュボード（Web UI） | 判断待ち一覧／活動ログ／利用量・リミットモニターの表示、ワンタップ承認・却下の入力 | Next.js（React） |
| オーケストレータ | GitHub Issuesのポーリング、状態集約、指示コメントの検知・ディスパッチ、Discordへの通知送信 | Pythonポーリングスクリプト（PoC-Aの`instruction_watcher.py`を発展） |
| Agent Runner | 実際にコードを書く実行単位。プロジェクトごとにgit worktreeで隔離し、ディスパッチ時にワンショットで起動 | Claude Code CLI（`claude -p`） |
| データ層 | タスク状態・指示履歴の正 | GitHub Issues/Projects |
| 通知 | 判断待ち発生時にモバイルへ知らせる（ダッシュボードでの定期確認運用が基本、Discordは補完） | Discord（Channels） |

### コンポーネント間の通信方式

- オーケストレータ⇄GitHub間、オーケストレータ⇄Agent Runner間ともに**ポーリングに統一**する。
- Webhook/GitHub Appは、外部から到達可能な公開エンドポイント（またはsmee.io等のトンネル）を必要とし、「ローカルPC完結・Tailscale閉域網」という前提と相性が悪いため採用しない。

## 2. エージェント実行基盤

- ローカルPC常駐方式を採用する。Claude Agent SDKによる自作Runnerは行わず、**Claude Code CLIをそのまま利用**する。
- **起動方式はワンショット実行**とする。オーケストレータが指示コメントを検知するたびに、対象プロジェクトのworktreeをカレントディレクトリとして `claude -p "<指示内容>" --resume <session-id>` を都度実行し、実行完了後プロセスは終了する。
  - アイドル時にプロセスが常駐しないためリソース効率が良い。
  - セッションの継続は `--resume` によるセッション再開を基本とし、必要に応じてissue本文・コメント履歴をコンテキストとして渡す設計とする。
  - [要件定義書 2-4](./requirements.md#2-4-agent-runnerの起動停止プロジェクト追加時の運用フロー)の「CLIコマンドによる手動起動・停止」は、この方式では「プロジェクトをRunner対象として有効化／無効化する」（オーケストレータのポーリング対象に含めるかどうか）という意味に読み替える。実際のプロセス実行はディスパッチ時のみ発生する。
- **プロセス分離方式**: プロジェクトごとにgit worktreeで隔離する。コンテナ（Docker）による隔離は[9章](#9-実行環境)の理由によりMVPでは採用しない。

## 3. タスク・状態管理

- 独自DBは新設せず、**GitHub Issue/Projectsを正**として扱う。
- 状態遷移は単一の状態ラベルを付け替える方式とし、同時に複数の状態ラベルが付与されることはない：

  ```
  status:todo → status:in-progress → needs-human-decision → status:in-review → (close)
  ```

  - 未着手: `status:todo`
  - 作業中: `status:in-progress`
  - 判断待ち: `needs-human-decision`（[要件定義書 2-2](./requirements.md#2-2-判断が必要な項目の判定規約)で確定済みのラベル）
  - レビュー待ち: `status:in-review`（PR作成済み）
  - 完了: ラベルではなくissueクローズで表現する

- **冪等な状態遷移設計**: PoC（[poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md) 1章）で `gh issue edit --remove-label X --add-label Y` が非atomicであることが判明している。オーケストレータ・Agent Runner双方とも、ラベルを更新する際は**現在のラベル状態を確認してから、必要な操作だけを個別に実行する**設計とし、失敗時にリトライしても安全な冪等操作にする。

## 4. ダッシュボード・オーケストレーション

- **データ層**: GitHub APIのポーリング（[1章](#1-全体構成)参照。Webhookは不採用）。
- **表示層**: Next.js（React）を採用する。1人運用・ローカルPC常駐が前提のため大規模なバックエンド分離は不要だが、将来のワンタップ操作等のUI拡張のしやすさを優先する。
- **AIへの指示導線**: 案A（GitHub issueコメント経由）でMVPを構築する。ダッシュボード上のワンタップ承認・却下（[要件定義書 2-7](./requirements.md#2-7-承認却下操作の要件)）も、内部的にはissueへのコメント投稿として実装する。専用API（案B）は将来拡張とする。

## 5. モデルルーティング

- MVPでは**LiteLLM Proxyを導入しない**。Agent RunnerはClaude Code CLIを直接利用し、Anthropic API従量課金ではなくClaude Code Pro/Maxプラン等のサブスクリプションを利用する（[要件定義書 2-5](./requirements.md#2-5-モデル選択方針)）。
- 将来ローカルLLMを併用する場合、LiteLLM Proxy等によるモデルルーティング層の追加を検討する。ただしClaude Code CLIはAPIエンドポイントを経由しないサブスクリプション利用のため、モデルルーターを挟む構成自体を将来拡張時に別途設計し直す必要がある点に留意する。
- Claude/ローカルLLMの使い分けポリシーの実装方針（オーケストレータ側 or Runner側）は、ローカルLLM併用が将来拡張のスコープであるためMVPでは決定しない。

## 6. 通知・承認フロー

- Claude Code Remote ControlのPush通知は実機検証で信頼性が確認できなかった（[要件定義書 2-6](./requirements.md#2-6-通知要件)）ため、Remote Controlには依存しない。
- **Discord**をChannelsとして採用し、判断待ち発生時にオーケストレータからDiscordへ通知を送信する。
- 主な利用シーン（就寝前後の確認、PC前レビュー）を踏まえ、ダッシュボードでの定期確認運用を基本としつつ、Discord通知を即時性の補完として併用する。

## 7. 権限管理・安全対策

- Agent Runnerはプロジェクトごとにgit worktreeで隔離し、**worktreeディレクトリ内ではフル自動実行**（`--dangerously-skip-permissions` 相当）を許可する。
- worktreeディレクトリという境界自体を隔離の安全壁とし、コマンド単位でのホワイトリスト／ブラックリスト管理は行わない（実装コストと1人運用という運用体制のバランスを踏まえた判断）。
- コンテナによる追加隔離は将来拡張とする。

## 8. ネットワーク構成

- 同一Wi-Fi内・外出先を問わず、**Tailscaleのネットワーク境界のみ**でダッシュボード・Agent Runnerへのアクセスを保護する。mDNS/固定IPによる同一Wi-Fi内限定アクセスは採用せず、Tailscale経由に一本化する。
- アプリケーションレベルの追加認証（Basic認証等）は設けない。

## 9. 実行環境

- PoC環境ではDockerのネットワーク関連操作（`docker network create`等）が恒常的にハングする問題が確認された（[poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md) 2章）。本番PC環境での動作確認は未実施のため、MVPでは**Dockerを使わずネイティブ構成**（Homebrew/pip等）を採用する。
- 将来Docker採用を検討する場合は、実際に運用するPC環境で事前にネットワーク機能の動作確認を行う。

## 参考

- [要件定義書](./requirements.md)
- [architecture-and-challenges.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/architecture-and-challenges.md)
- [poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md)

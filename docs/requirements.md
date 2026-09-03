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
- Claude Codeの利用量／リミット到達状況モニター（日単位・モデル別の使用量表示、リミット到達時の解除予定時刻表示。[3-4](#3-4-コスト制約)参照）
- 新しい指示を出す入力欄（自由記述のテキストボックス。既存issueへの追加指示、新規タスクの作成の両方に使用。[2-3](#2-3-aiへの指示出し導線)参照）
- プロジェクト別サマリは今回のMVPでは対象外とする。

### 2-2. 「判断が必要な項目」の判定規約

- `needs-human-decision` ラベルの有無のみで判定する。
- 担当者(assignee)の有無による判定は、PoC（[poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md) 1章）で識別力が無いことが確認済みのため採用しない。
- エージェントが「人間の判断が必要」と自ら判断したタイミングで能動的にラベルを付与する運用規約とする。

### 2-3. AIへの指示出し導線

- 案A（GitHub issueコメント経由）でMVPを開始する。
  - ダッシュボード上のワンタップ操作（[2-7](#2-7-承認自由記述による指示出しの要件)）は、内部的にissueへのコメント投稿として実装する。
  - オーケストレータ役のポーリングスクリプトが新規コメントを検知し、Agent Runnerへディスパッチする（[poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md) PoC-A参照）。
- ワンタップ承認に加え、ダッシュボードのテキストボックスから**自由記述のプロンプトで指示を出せる**ようにする（[2-7](#2-7-承認自由記述による指示出しの要件)）。対象は以下の両方とする。
  - **既存issueへの追加指示**: issueの状態を問わず送信可能とする（作業中のプロジェクトへの割り込み指示も含む）。
  - **新規タスク（新規issue）の作成**: 対象プロジェクトを選び、自由記述のプロンプトから新しいissueを作成する。作成と同時にAgent Runnerへ即時着手させるか、todoとして登録するだけで後から着手させるかを選べるようにする。
- 専用API経由（案B）は将来拡張とする。レイテンシは低いが実装コストが高いため、MVPのスコープには含めない。

### 2-4. Agent Runnerの起動・停止・プロジェクト追加時の運用フロー

- MVPでは、CLIコマンドによる手動起動・停止とする。
- プロジェクト追加時も、プロデューサーが手動でRunnerを起動する運用とする。
- オーケストレータによる自動起動・停止・スケーリングは将来拡張とする。

### 2-5. モデル選択方針

- issue #148での検討を経て、コード変更を伴う自走タスク（Agent Runnerでのコード編集そのもの）の実行手段は、プロジェクトごとにユーザーが選択できる方針とする（従来の「自走タスク本体はClaude Codeのみ」という限定は撤廃）。選択肢は以下の2つ。
  - **(A) Claude Code CLI直利用**: Anthropic APIの従量課金は使わず、Claude Code Pro/Maxプラン等のサブスクリプション契約を利用する（[3-4](#3-4-コスト制約)参照）。Agent RunnerはClaude Code CLIプロセスとしてプロジェクトごとに起動する。
  - **(B) LiteLLM Proxy経由**: Claude Code CLIの接続先をLiteLLM Proxyへ切り替え、他社プロバイダのモデル・ローカルLLMを自走タスク本体の実行に利用する。この経路は（Claudeモデルを指定した場合を含め）従量課金に切り替わる（[3-4](#3-4-コスト制約)参照）。
  - デフォルトの実行手段はダッシュボードのプロジェクト設定UIでプロジェクトごとに設定し、issueコメントでの都度指示によりデフォルトから一時的に変更できる（設定方式・導入方式の詳細は[architecture.md 5章](./architecture.md#5-モデルルーティング)・[basic-design.md 4章](./basic-design.md#4-モデルルーター設定設計)参照。設定画面自体は別issueで扱う）。
  - 自走タスク本体の実行手段として(B) LiteLLM Proxy経由でローカルLLMを選択する場合、ツール呼び出し（Function Calling）の信頼性がモデルサイズに強く依存し不安定であることがPoC（[architecture-and-challenges.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/architecture-and-challenges.md) 2-4節）で確認されている点に留意する。この制約は、後述する「ローカルLLMの補助的併用」方針（自走タスク本体ではなくAgent Runnerが直接呼び出す補助用途）そのものには影響しない。
- **ローカルLLMの補助的併用**: 自走タスク本体とは別に、Function Calling非依存または低リスクな補助用途（コードレビュー支援・デバッグ調査の下調べ・日本語ドキュメント生成）に限り、ローカルLLM（Ollama）を併用する。Agent Runner（Claude Code CLI）自身が、後述のタスク種別ごとの推奨モデルに従って必要に応じて呼び出す。モデルの利用可否確認はMCP `ollama-client`でよいが、実際の生成呼び出しはOllama REST APIを直接呼び出す`ollama-bench`コマンド経由に一本化している（MCP `ollama-client`はOllama REST APIのトークン数・処理時間メトリクスを返さず利用量を記録できないため。issue #107）（呼び出し方式・モデルルーティング層の要否の設計判断は[architecture.md 5章](./architecture.md#5-モデルルーティング)、実装仕様は[basic-design.md 4章](./basic-design.md#4-モデルルーター設定設計)参照）。
  - 根拠となる調査: `research-log` [`log/2026/08/local-llm-benchmark/README.md`](https://github.com/nosetech/research-log/blob/main/log/2026/08/local-llm-benchmark/README.md)（issue [#70](https://github.com/nosetech/research-log/issues/70)、`qwen2.5:7b` / `gemma2` / `qwen2.5-coder:7b` の検証）、[`log/2026/08/local-llm-benchmark-additional/README.md`](https://github.com/nosetech/research-log/blob/main/log/2026/08/local-llm-benchmark-additional/README.md)（issue [#72](https://github.com/nosetech/research-log/issues/72)、`granite-code:8b` / `deepseek-coder-v2:16b` / `codestral:22b` の追加検証）
  - タスク種別ごとの推奨モデル:
    - コードレビュー支援 → `deepseek-coder-v2:16b`（検証6モデル中、指摘の網羅性・日本語安定性・実装可能な修正提案のバランスが最良）
    - デバッグ調査の下調べ → `deepseek-coder-v2:16b`（原因特定と動作する修正コードの両立で最も安定）
    - 日本語ドキュメント生成 → `gemma2`（中国語混入がなく日本語の一貫性が最も高い。ただし4例題に文書生成は含まれておらず、コードレビュー例題での説明の丁寧さからの類推であるため、実運用開始時に改めて品質を確認すること）
    - 上記以外・速度優先の簡易チェック → `qwen2.5-coder:7b`（VRAM内に収まる7B級で最速の76〜79 tok/s帯）
  - 不採用としたモデル: `granite-code:8b`（デバッグ・コードレビュー例題で日本語出力が意味不明な単語の反復やスペイン語化に陥り、日本語プロダクト用途に耐えない）、`codestral:22b`（RTX 3070のVRAM 8GBを大きく超過し4.6 tok/sまで速度低下、実用性が低い）
- 自走タスク本体の実行手段選択（上記(B)）のためLiteLLM Proxyを導入する。ローカルLLMの補助的併用（コードレビュー支援・デバッグ調査の下調べ・日本語ドキュメント生成）は引き続きLiteLLM Proxyを経由せず、MCP `ollama-client`・`ollama-bench`コマンドを介してAgent Runnerが直接呼び出す構成のままとする（用途・計測経路が自走タスク本体とは異なるため統合しない。詳細は[architecture.md 5章](./architecture.md#5-モデルルーティング)参照）。

### 2-6. 通知要件

- Claude Code Remote ControlのPush通知は実機検証（Android、3回）で一度も届かず、信頼性に課題があることが判明している（[poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md) 7-1節）。
- Slack（Incoming Webhook）を併用し、Push通知の信頼性をプラットフォーム側に委ねる形で補完する（Claude Code純正のChannelsプラグインではなく、オーケストレータから直接Slackへ通知する方式。[architecture.md 6章](./architecture.md#6-通知承認フロー)参照）。
- 主な利用シーンが「就寝前後」「PC前レビュー」中心で即時性の優先度が低いことも踏まえ、Push通知の到達を前提にしすぎない設計とする。

### 2-7. 承認・自由記述による指示出しの要件

- ダッシュボード上でワンタップでの承認操作を提供する（[2-3](#2-3-aiへの指示出し導線)の通り、内部的にはissueコメント投稿として実装）。押下時はYes/No確認のみで、コメント文の入力は不要とする。
- 却下（差し戻し）専用の操作は設けない。承認以外の意思表示（方針変更・保留等）は自由記述の指示で行う。
- 加えて、自由記述のテキストボックスから任意の指示を送れるようにする。既存issueへの追加指示（状態を問わない）と、新規タスクの作成（即時着手／todo登録の選択式）の両方に対応する。

## 3. 非機能要件

### 3-1. セキュリティ・認証

- アプリケーションレベルの追加認証（Basic認証等）は設けない。
- **MVPでは同一LAN内からのアクセスのみを前提**とし、ネットワーク境界のみで保護する（外出先からの利用は考慮しない）。Tailscale等による同一LAN外（外出先）からのアクセス対応は将来拡張とする（[4-2](#4-2-将来拡張とする範囲)参照）。

### 3-2. 権限管理・安全対策

- プロジェクトごとにgit worktreeで隔離し、隔離範囲内では自動実行（`--dangerously-skip-permissions` 相当）を許可する。
- コンテナ（Docker）による隔離は、[4-2](#4-2-対象外とする既存ツールpoc結果の扱い)の理由によりMVPでは採用しない。worktree隔離のみとし、コンテナ隔離は将来拡張とする。

### 3-3. 可用性

- `caffeinate` 等によるPCスリープ防止を運用前提とする。
- ネットワーク切断時は、Claude Code Remote Control標準の自動再接続に依存する。

### 3-4. コスト制約

- [2-5](#2-5-モデル選択方針)の(A) Claude Code CLI直利用を選択した場合、Anthropic APIの従量課金は使わず、Claude Code Pro/Maxプラン等のサブスクリプション契約の範囲内で運用する。追加コストを支払っての即時再開は行わない。
- [2-5](#2-5-モデル選択方針)の(B) LiteLLM Proxy経由を選択した場合、自走タスク本体の実行は他社プロバイダ・ローカルLLMを含め従量課金の経路として扱う（ローカルLLM自体の生成に金銭コストは発生しないが、他社プロバイダと同じ経由先・同じ利用量計測方式で扱う。[architecture.md 5章](./architecture.md#5-モデルルーティング)参照）。プロバイダ・モデルの種類による利用制限は設けず、実行手段の選択と同様にユーザーの判断に委ねる。従量課金の予算上限による自動ブロックは導入しない（DBなし運用のため機能しない。可視化のみ）ため、コスト超過の防止は利用者自身の判断に委ねる。なお、コードレビュー支援等のローカルLLM補助的併用（[2-5](#2-5-モデル選択方針)参照）はこの(B)の対象外であり、引き続きLiteLLM Proxyを経由しない。
- 利用リミット（レートリミット等）に達した場合は、Agent Runnerを一時停止し、プランのリセットタイミングまで待機する（(A)を選択している場合。(B)選択時は従量課金のため利用リミットという概念自体が当てはまらない）。
- ダッシュボードには利用量・リミット到達状況をモニターとして表示する（[2-1](#2-1-ダッシュボード表示項目)参照）。
- Anthropicアカウント側が内部管理するセッション5時間枠・週間上限に対する正確な消費率(%)は、Agent Runnerの実行結果（非対話の`-p`実行）からは取得できないことが判明した（issue #60）。そのため、正確な利用率(%)表示は行わず、Agent Runner実行のたびに得られるトークン数・コストを記録し、**日単位・モデル別の使用量**として表示する方式とする（[basic-design.md 2-2](./basic-design.md#2-2-データ取得仕様ポーリング)参照）。
- リミット到達時（`is_error: true`かつ`api_error_status: 429`）は、レスポンス中の自由文からリセット予定時刻を抽出し表示する。パース失敗時は生の文字列をそのまま表示するフォールバックを備える。

### 3-5. 運用体制

- issue #1の前提通り、1人運用（プロデューサー単一）を前提とする。
- 将来的な複数ユーザー対応・権限分離は考慮しない。

## 4. スコープ確定（MVP）

### 4-1. MVPに含める範囲

- ダッシュボード（判断待ち一覧／最近の活動ログ／利用量・リミットモニター、ワンタップ承認、自由記述による指示入力欄）
- GitHub issueコメント経由の指示出し（案A）。既存issueへの追加指示・新規タスク（issue）作成の両方に対応
- 自走タスク本体（コード変更）の実行手段はプロジェクトごとに選択可能（(A) Claude Codeのみ・Pro/Maxプラン等のサブスクリプション、または(B) LiteLLM Proxy経由の他モデル・ローカルLLM・従量課金。[2-5](#2-5-モデル選択方針)参照）
- コードレビュー支援・デバッグ調査の下調べ・日本語ドキュメント生成に限定した、MCP `ollama-client`・`ollama-bench`コマンド経由でのローカルLLM補助的併用（[2-5](#2-5-モデル選択方針)参照）
- 同一LAN内アクセスのみによる保護（アプリレベルの追加認証は設けない）
- プロジェクトごとのgit worktree隔離
- CLIコマンドによるAgent Runnerの手動起動・停止
- Slack（Incoming Webhook）併用による通知の信頼性補完
- 利用リミット到達時はプランのリセットまで待機（追加コスト支払いなし）

### 4-2. 将来拡張とする範囲

- 専用API経由の指示出し導線（案B）
- オーケストレータによるAgent Runnerの自動起動・停止・スケーリング
- コンテナ（Docker）によるプロジェクト隔離
- 複数ユーザー対応・権限分離
- Tailscale経由での同一LAN外（外出先）からのダッシュボードアクセス対応

### 4-3. 対象外とする既存ツール・PoC結果の扱い

- **Docker構成**: PoC環境（[poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md) 2章）でDockerのネットワーク関連操作が恒常的にハングする問題が発生し、Homebrew/pipによるネイティブインストールで回避した経緯がある。本番の実際のPC環境での動作確認は未実施のため、MVPではDockerを使わずネイティブ構成（Homebrew/pip等）を採用する。将来Docker採用を検討する場合は、本番PC環境での事前検証を行う。
- **Tailscale/WireGuard実機セットアップ**: issue #1のスコープ外（ユーザー自身の実機作業）としてPoC側で既に整理済み。本要件定義でもプロデューサー自身の作業として扱う（MVPでは同一LAN内アクセスのみのため、実機セットアップ自体は[4-2](#4-2-将来拡張とする範囲)のTailscale対応issueに着手する時点で行う）。

## 参考

- [existing-tools.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/existing-tools.md)
- [architecture-and-challenges.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/architecture-and-challenges.md)
- [poc-results.md](https://github.com/nosetech/research-log/blob/main/log/2026/07/autonomous-dev-orchestration/poc-results.md)

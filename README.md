# producer-desk

producer-deskは、プロデューサー1名が複数プロジェクト（3〜5件程度の同時進行を想定）のソフトウェア開発をAIエージェントに任せて監督するための、自走型AI開発オーケストレーションシステムです。GitHub issueに指示を書くと、[Claude Code](https://claude.com/product/claude-code) CLIによる「Agent Runner」がバックグラウンドで実装・PR作成まで自走し、人間の判断が必要な場面（設計判断・レビュー）だけダッシュボード経由で対応する運用を想定しています。

**開発ではなく利用したい場合**は、git cloneせず[GitHub Releases](https://github.com/nosetech/producer-desk/releases)から配布パッケージ（ビルド済みtarball）をダウンロードしてください。以下はその手順です。producer-desk自体の開発に参加する場合は[CONTRIBUTING.md](./CONTRIBUTING.md)を、内部設計を詳しく知りたい場合は[`docs/`](./docs/)を参照してください。

## 前提ソフトウェア

以下はOS側の前提としてあらかじめインストールしておく必要があります（配布パッケージには含まれません）。

- Node.js 20以降
- Python 3.11以降
- [GitHub CLI (`gh`)](https://cli.github.com/)（`gh auth login` 済みであること。画像・動画の添付には v2.99.0 以上を推奨。Privateリポジトリを管理対象にする場合は `config/projects.yaml` の `github_token` も設定する。[SETUP](dist/SETUP.md)参照）
- [Claude Code CLI](https://claude.com/product/claude-code)（自走タスク本体の既定の実行手段。Pro/Maxプラン等のサブスクリプション認証済みであること）
- macOS（DBバックアップのlaunchd連携を含め、動作確認はmacOSのみ）

自走タスク本体の実行手段は、上記のClaude Code CLI直利用（サブスクリプション内、追加コストなし）に固定されているわけではなく、プロジェクトごとに任意で[LiteLLM Proxy](https://docs.litellm.ai/)経由に切り替え、他プロバイダ（OpenAI等）やローカルLLM（Ollama等）を従量課金で利用することもできます。使わない場合は以下の追加設定は不要です（詳細は後述の「LiteLLM Proxyのセットアップ（任意）」参照）。

Dockerは使いません（ネイティブ構成での動作を前提としています）。

## インストール

任意のディレクトリに配布パッケージ（tarball）を展開します。

```bash
tar xzf producer-desk-<version>.tar.gz
cd producer-desk-<version>
```

## 初期設定

### 対象プロジェクトの設定

`config/projects.yaml.example` をコピーして `config/projects.yaml` を作成し、AIに任せたい対象リポジトリと、そのリポジトリを展開するworktreeパスを記載します。

```bash
cp config/projects.yaml.example config/projects.yaml
```

```yaml
projects:
  - repo: nosetech/project-a
    worktree_path: /Users/producer/worktrees/project-a
```

対象リポジトリのworktree自体は事前に用意しておく必要があります。プロジェクトを追加・変更した場合は、このファイルを編集した上でproducer-deskを再起動してください。

上記の「対象リポジトリへの状態ラベル作成」「worktreeの用意」「このファイルへの追記」は、`scripts/add_project.sh`で1コマンドにまとめて行えます（`gh auth login`済みであること）。

```bash
./scripts/add_project.sh nosetech/project-a /Users/producer/worktrees/project-a
```

ベースブランチは省略時`develop`で、対象リポジトリに無ければ`main`→`master`の順にフォールバックします（3番目の引数で明示的に指定することもできます）。既にラベル・worktree・エントリが存在する場合はそれぞれスキップされるため、何度実行しても安全です。実行後は案内に従ってproducer-deskを再起動してください（自動再起動は行われません）。

### Slack通知設定（任意）

判断待ち・レビュー待ち発生時のSlack通知を使う場合は、`SLACK_WEBHOOK_URL` にIncoming WebhookのURLを設定します。未設定の場合、通知処理は単にスキップされます（起動エラーにはなりません）。

**方法A: `.env` ファイルに記載する（推奨）**

`.env.example` をコピーして `.env` を作成し、`SLACK_WEBHOOK_URL` の行のコメントを外してURLを記載します。起動のたびに自動で読み込まれるため、以後は環境変数を都度exportする必要がありません。`ORCHESTRATOR_PORT`・`DASHBOARD_PORT`・`LAN_IP`・`TAILSCALE_IP`（後述）も同様にここで設定できます。

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

`.env` に記載した値とシェルでexportした値の両方が存在する場合、`.env` 側の値で上書きされます。恒常的な設定は方法A、その場限りの一時的な上書きには方法Bを使う、という使い分けを推奨します。

### LiteLLM Proxyのセットアップ（任意）

自走タスク本体をプロジェクトごとにClaude Code CLI直利用以外の実行手段に切り替えたい場合（他プロバイダのAPI・ローカルLLMを従量課金で使いたい場合）は、LiteLLM Proxyを導入します。使わない場合、以下の設定は不要です。

`config/litellm_config.yaml.example` をコピーして `config/litellm_config.yaml` を作成し、`model_list`にプロジェクトごとの実行手段として使いたいモデルを定義します。

```bash
cp config/litellm_config.yaml.example config/litellm_config.yaml
```

```yaml
model_list:
  # 例1: OpenAIのモデルをproject-aの実行手段として使う場合
  - model_name: project-a-openai-gpt4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY
    model_info:
      repo: nosetech/project-a

  # 例2: ローカルLLM（Ollama）をproject-bの実行手段として使う場合
  - model_name: project-b-ollama-qwen
    litellm_params:
      model: ollama/qwen2.5-coder:7b
      api_base: http://127.0.0.1:11434
      num_ctx: 32768
    model_info:
      repo: nosetech/project-b
      max_session_tokens: 24000
      max_session_turns: 20
```

`litellm_params.model`にはプロバイダAPI側のモデル指定を、プロバイダAPIキーが必要な場合は`api_key`に`os.environ/<環境変数名>`の形式で参照する環境変数名を指定します（APIキー自体をこのファイルに直接書かないでください）。ローカルLLMの場合は`api_base`に接続先URLを指定します。`model_info.repo`には、この`model_name`を実行手段として使うプロジェクトのリポジトリ名を記載します（LiteLLM ProxyはPostgreSQL等のDBを使わない運用のため、プロジェクトごとの仮想キー発行は行わず、モデルエイリアス単位で利用量の帰属先リポジトリを区別する仕組みになっています）。

ローカルLLM（Ollama等）を使う場合、以下の2種類の追加設定を検討してください（いずれも省略可、上のyaml例では設定済み）。

- **`litellm_params.num_ctx`（モデルのコンテキストウィンドウサイズ、必須推奨）**: 未指定の場合Ollama自体の既定値2048トークンが使われますが、Claude Code CLIの自動コンテキスト圧縮（compaction）時のプロンプトは会話履歴全体を含むためこれを容易に超過し、「the prompt is longer than the context length currently available to the model」という400エラーでセッションが異常終了します。値はOllamaホストのVRAM/RAM容量に収まる範囲で実機検証して決めてください（大きすぎるとOOMの恐れがあります）。
- **`model_info.max_session_tokens` / `max_session_turns`（会話量・ターン数の上限、いずれも省略時は無制限）**: Claude Code CLI自身の自動コンテキスト圧縮は`--autocompact`が100k〜1Mトークン範囲でしか設定できず、`num_ctx`程度の小さなモデル容量には間に合いません。そのためオーケストレータ側でこれらの上限を検知し、超過した回の完了処理（コメント投稿・ラベル遷移）を通常通り行った上で、セッションをリセットする旨のコメントを追加投稿します（次回のディスパッチから自然に新規セッションとして開始されます）。`max_session_tokens`は`num_ctx`の7〜8割程度、`max_session_turns`は「`max_session_tokens` ÷ 1ターンあたりに消費するトークン数（実機の利用量記録等から見積もったもの）」より小さい値を目安にしてください。

設定後、以下で起動・停止します。

```bash
./bin/litellm_proxy_start.sh
./bin/litellm_proxy_stop.sh
```

初回起動時、LiteLLM Proxy専用の`litellm_proxy/.venv`を自動作成し`litellm[proxy]`をインストールします（オーケストレータ本体のvenvとは分離されています）。bindポートは環境変数`LITELLM_PROXY_PORT`（既定4000）、オーケストレータ・Agent Runnerが接続する先は`LITELLM_PROXY_URL`（既定`http://127.0.0.1:<LITELLM_PROXY_PORT>`）で上書きできます（他のポート系環境変数と同様、`.env`に記載しておくと起動のたびに自動で読み込まれます）。

起動後、ダッシュボードの「使い方」節で説明する設定ダイアログから、プロジェクトごとに実行手段をLiteLLM Proxy経由へ切り替えます。issueコメントで都度切り替えることもできます（後述）。

**注意**: LiteLLM Proxy経由を選んだ場合、指定したモデルがClaudeモデルであっても、Claude Code CLI直利用時のサブスクリプション枠内（追加コストなし）ではなく、プロバイダAPIの従量課金に切り替わります。

#### LiteLLM Proxyの常時起動（macOS launchd、任意）

`./bin/litellm_proxy_start.sh`は手動起動・PIDファイル管理のみのため、macOSの再起動やログアウト、プロセスクラッシュ時に自動復旧しません。ログイン時の自動起動・クラッシュ時の自動再起動をさせたい場合は、`scripts/com.nosetech.producer-desk.litellm-proxy.plist.example`を使ってlaunchdのLaunchAgentとして常駐化します。

```bash
cp scripts/com.nosetech.producer-desk.litellm-proxy.plist.example \
  ~/Library/LaunchAgents/com.nosetech.producer-desk.litellm-proxy.plist
```

コピー後のファイル内の `/path/to/producer-desk` を、展開先の実際の絶対パスに書き換えます（`ProgramArguments`・`WorkingDirectory`・`StandardOutPath`・`StandardErrorPath`の4箇所）。`litellm_proxy/.venv`が未作成の場合は、launchd起動時のネットワークアクセスを避けるため、先に`./bin/litellm_proxy_start.sh`を一度手動実行して作成しておいてください（既に起動中の場合は`./bin/litellm_proxy_stop.sh`で停止してから進めます）。

```bash
launchctl load -w ~/Library/LaunchAgents/com.nosetech.producer-desk.litellm-proxy.plist
```

読み込み後は自動的に起動し、プロセスが落ちた場合も`KeepAlive`により自動再起動されます。停止する場合:

```bash
launchctl unload ~/Library/LaunchAgents/com.nosetech.producer-desk.litellm-proxy.plist
```

**注意**: `./bin/litellm_proxy_start.sh` / `stop.sh`（PIDファイル方式）とlaunchd管理は併用できません（ポートの二重bind・PIDファイルの不整合が起きます）。launchd化した後は、起動・停止を`launchctl load -w` / `unload`に一本化してください。

### 補助モデル（MCP）の使用量を記録する（任意）

producer-deskが使用量を記録するのは、次の2経路です。

| 経路                                                                 | 記録                                                              |
| -------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Agent Runner本体（Claude Code CLI直利用、またはLiteLLM Proxy経由）   | 自動で記録されます（LiteLLM Proxy経由は上記のコールバックが記録） |
| プロジェクトの作業中にAgent Runnerが補助的に呼ぶ別モデル（Ollama等） | 呼び出し方を指示しない限り記録されません                          |

後者はLiteLLM Proxyを経由せず、MCP（例: `ollama-client`）などでAgent Runnerが直接呼び出す構成です。producer-deskは、このような補助モデルの併用方針（どの作業で、どのモデルを使うか）を共通の指示文としては与えません。プロジェクトごとに、対象リポジトリの`CLAUDE.md`や作業指示に書いてください。ただしMCP `ollama-client`の`ollama_chat`ツールは、トークン数・処理時間を返さないため、そのままでは使用量を記録できません。

Ollamaのモデルについて使用量を記録したい場合は、生成呼び出しを`ollama-bench`コマンドに`--record`を付けて実行させます（Ollama REST APIを直接呼び出し、`config/usage.db`の利用量記録に書き込みます）。`ollama-bench`はオーケストレータ自身のvenvにしか入っておらず、対象プロジェクトのworktreeからはPATH解決できません。そのためAgent Runnerの子プロセスには、解決済みの絶対パスが環境変数`OLLAMA_BENCH_PATH`として設定されています。`CLAUDE.md`には、コマンド名ではなくこの環境変数を使うよう書いてください。

```markdown
## ローカルLLMの併用

コードレビュー支援・日本語ドキュメント生成など、コード変更を伴わない補助作業では、
必要に応じてローカルLLM（Ollama）を併用してよい。

- 生成の呼び出しは、MCP `ollama_chat`ではなく、Bashツールで環境変数`$OLLAMA_BENCH_PATH`が
  指す`ollama-bench`コマンドを使う（`ollama-bench`というコマンド名では呼ばない）。
- 必ず`--record --repo <owner/repo> --issue-number <issue番号>`を付ける。repoとissue番号は、
  Agent Runner起動時のsystem promptに記載された、取り組み中のissueのものを使う。
- プロンプトは`mktemp`で毎回一意な一時ファイルに書き出して渡す。
- 例: `PROMPT_FILE=$(mktemp); ... > "$PROMPT_FILE"; "$OLLAMA_BENCH_PATH" deepseek-coder-v2:16b "$PROMPT_FILE" --record --repo owner/repo --issue-number 12`
- モデルの利用可否の確認は、MCP `ollama_list` / `ollama_ps`でよい。
```

注意点:

- `ollama-bench`の対象はOllamaのみです。Ollama以外のプロバイダのモデルをMCP等で補助的に呼ぶ場合、producer-deskは使用量を記録できません。使用量を記録したい場合は、そのモデルをLiteLLM Proxy経由（上記）のモデルエイリアスとして定義し、Agent Runner本体の実行手段として選択してください。
- 記録先のissue番号は`--issue-number`で指定します。指定しなかった場合は`0`（プロジェクト単位の集計）として記録されます。
- Agent Runnerが指示を守らない場合、記録は残りません。指示の記載は`CLAUDE.md`に書いたうえで、ダッシュボードの利用量表示を確認してください。

## 起動・停止

```bash
./bin/start.sh
```

初回起動時、`orchestrator/.venv` を自動作成し、同梱の`orchestrator/dist/*.whl`をインストールしてから起動します（ネットワークアクセス不要、`pip install`のみ）。dashboardは`npm install`・ビルド不要のビルド済みNext.js standalone出力をそのまま起動します。

- orchestrator: `http://127.0.0.1:8787`（環境変数 `ORCHESTRATOR_PORT` で上書き可。dashboardの接続先もこのポートに自動追従する）
- dashboard: `http://127.0.0.1:3000`（環境変数 `DASHBOARD_PORT` で上書き可）

同一LAN内の別端末（スマートフォン等）からdashboardにアクセスする場合は、自機のLAN IPを環境変数 `LAN_IP` に設定してから起動します。

```bash
LAN_IP=192.168.1.xx ./bin/start.sh
```

外出先からTailscale経由でアクセスする場合は、自機のTailscale IPを環境変数 `TAILSCALE_IP` に設定して起動します（`LAN_IP`とは同時に指定できません。手順・確認方法は[`docs/basic-design.md` 6-2](./docs/basic-design.md#6-2-ネットワークアクセスの認証設計)参照）。

```bash
TAILSCALE_IP=$(tailscale ip -4) ./bin/start.sh
```

アプリケーションレベルの追加認証（Basic認証等）は設けていないため、信頼できるLAN内、またはtailnet内でのみ利用してください。

停止する場合:

```bash
./bin/stop.sh
```

orchestrator（バックエンド）とdashboard（フロントエンド）を片方だけ起動・停止したい場合（thothのように、プロセスごとに起動・停止するアプリ管理ツールへ登録する場合など。issue #326）は、個別スクリプトを使います。

```bash
./bin/backend_start.sh   # orchestratorのみ起動（バックグラウンドで起動して即終了）
./bin/backend_stop.sh    # orchestratorのみ停止
./bin/frontend_start.sh  # dashboardのみ起動（npm ci + ビルド + next start）
./bin/frontend_stop.sh   # dashboardのみ停止
SKIP_BUILD=1 ./bin/frontend_start.sh  # npm ci・ビルドを省略して再起動のみ（ビルド済みの場合のみ）
```

PIDファイル（`logs/orchestrator.pid`・`logs/dashboard.pid`）・ログ・環境変数は`./bin/start.sh` / `./bin/stop.sh`と同一のため、一括と個別を混在させても停止できます（例: 個別に起動したものを`./bin/stop.sh`で止める）。

### 本体の常時起動（macOS launchd、任意）

`./bin/start.sh`はPIDファイル方式の手動起動のため、macOSの再起動・ログアウト・プロセスクラッシュ時に自動復旧しません。自動復旧させたい場合は、同梱の`./bin/service.sh`でorchestrator・dashboardをlaunchdのper-user LaunchAgentとして登録します。**ログイン中のみ動作する**（ログイン前の起動が必要なLaunchDaemonは対象外です）。

```bash
./bin/service.sh install     # plist生成・登録・起動（再実行で設定変更を反映）
./bin/service.sh status      # 登録・稼働状況
./bin/service.sh restart     # 再起動（.env / config/projects.yaml の変更反映に使う）
./bin/service.sh stop        # 停止（次回ログインまたは start まで停止）
./bin/service.sh start       # 停止中のサービスを起動
./bin/service.sh uninstall   # 停止・登録解除・plist削除
```

- `install`は、`config/projects.yaml`が無い場合（クラッシュループになるため）、`gh`・`claude`・`node`が見つからない場合、`LAN_IP`と`TAILSCALE_IP`を同時指定した場合に失敗します。`orchestrator/.venv`が無ければ`start.sh`と同様に作成します
- launchd下の`PATH`には、`install`実行時に`gh`・`claude`・`node`のあるディレクトリが自動で設定されます（別のPATHを使いたい場合は環境変数`SERVICE_PATH`で明示します）。`.env`は`start.sh`と同じ処理で起動時に読み込まれるため、`SLACK_WEBHOOK_URL`等の転記は不要です。`ORCHESTRATOR_PORT`・`DASHBOARD_PORT`・`LAN_IP`・`TAILSCALE_IP`の扱いも`start.sh`と同じ（dashboardの`ORCHESTRATOR_URL`は実行時の環境変数のため、ポートを変えても再ビルドは不要です）
- クラッシュ時は自動再起動されます（再起動間隔は30秒以上に制限されます）
- ログは`start.sh`と同様に`logs/orchestrator.log`・`logs/dashboard.log`が日次ローテーションされます。起動前のエラー（`.env`や`projects.yaml`の不備等）は`logs/<orchestrator|dashboard>.launchd.stderr.log`に出ます
- **`./bin/start.sh` / `./bin/stop.sh`とは併用できません**。launchd登録中に`start.sh`を実行した場合、`start.sh`手動起動中に`service.sh install`/`start`/`restart`を実行した場合は、案内メッセージを出して失敗します。手動運用に戻す場合は`./bin/service.sh uninstall`を実行する
- Macがスリープしている間は、LAN・Tailscale経由でdashboardに到達できません。常時利用する場合は、システム設定の省エネ設定でスリープを抑止する（または`caffeinate`を使ってください）（本スクリプトの対象外）
- `bin/dev_instance.sh`による確認用インスタンス（git clone環境専用、18000番台ポート）とは独立しており、干渉しません

手動でlaunchdに登録する場合の参考として、`install`が生成するplistの元になる例を`scripts/com.nosetech.producer-desk.orchestrator.plist.example`・`scripts/com.nosetech.producer-desk.dashboard.plist.example`に残しています（通常は`service.sh`を使ってください）。

## 使い方

起動後、ブラウザで`http://127.0.0.1:3000`（またはLAN IP経由）を開くとダッシュボードが表示されます。

- **判断待ち一覧**: `needs-human-decision`ラベルが付いたissue（Agent Runnerが自ら「人間の判断が必要」と判断して停止したもの）が横断的に並びます。各カードには、AIの最終応答に「判断が必要な事項」セクションがあればその判断事項が番号付きで表示されます（無ければ最新コメントの要約）。「返信」から自由記述で指示（判断の回答・方針変更・追加情報の提供等をそのままコメント投稿する）すると、Agent Runnerが再開します。専用の「却下」操作はなく、方針を変えたい場合も自由記述で伝えます。
- **レビュー待ち一覧**: `status:in-review`ラベルが付いたissue（Agent RunnerがPRを作成し終えたもの）が並びます。紐づくPRへのリンクが表示されるので内容を確認し、「承認」でそのPRをsquash mergeしてissueをクローズします。差し戻したい場合は自由記述で修正指示を送ると、Agent Runnerが同じPRブランチで対応を続けます。
- **新規タスクの作成**: プロジェクトを選び、タイトルと自由記述のプロンプト（指示内容）を入力してissueを新規作成できます。「即時着手」を選ぶとすぐにAgent Runnerがディスパッチされ、「todo登録」を選ぶと`status:todo`のまま登録だけ行われ、後で着手を指示できます。
- **プロジェクトの並行状況**: プロジェクト（リポジトリ）ごとに、直近更新issueの状態と状態別のissue件数が表示されます。ラベルは付いているのに対応するAgent Runnerのプロセスが実際には動いていない異常（`status:in-progress`のまま停止している等）は警告アイコンで示されます。
- **プロジェクトの実行設定**: 各プロジェクトチップの歯車アイコンから設定ダイアログを開き、そのプロジェクトの自走タスク本体の実行手段（既定の「Claude Code」、または前述の「LiteLLM Proxy経由」）を選択・保存できます。「LiteLLM Proxy経由」を選ぶ場合は、`config/litellm_config.yaml`の`model_list`で定義したモデルエイリアスを併せて選びます（未定義の場合はその旨が表示され、先に設定ファイルを編集する必要があります）。ここでの設定はプロジェクトの既定値で、後述のissueコメントによる都度上書きが優先されます。
- **Slack通知**: 判断待ち・レビュー待ちが新規に発生すると、設定したSlackチャンネルに通知が届きます（起動時点で既に判断待ち・レビュー待ちだったissueは再通知しません）。

GitHub issueに直接コメントを書いても（ダッシュボードを介さなくても）、次回ポーリング（最大5分後）でAgent Runnerへの指示として検知されます。ただし`status:todo`等の状態ラベル（上記5種）が一つも付いていないissueは、producer-deskの管理対象外として扱われるため、コメントしても処理は開始されません（設計ドキュメントの議論用issue等、producer-deskが起票・着手していないissueへの誤起動を防ぐため）。着手させたい場合は、ダッシュボードの「新規タスクの作成」から登録するか、対象issueに`status:todo`ラベルを付与してください。

個別issueに限定してその場限りで実行手段を切り替えたい場合は、issueコメント本文の独立した行に`/model claude_code`（Claude Code CLI直利用に戻す）または`/model litellm:<モデルエイリアス>`（`config/litellm_config.yaml`の`model_name`を指定、例: `/model litellm:project-a-openai-gpt4o`）と書きます。この指定はそのissueに保存され、プロジェクトの既定設定より優先して以降のディスパッチ（`--resume`による再開時も含む）に使われ続けます。ディレクティブ行だけを送った場合（作業指示を伴わない場合）は、実行手段の切り替えのみとして扱われ、Agent Runnerは直前までの作業を継続します。

## ログ

各種ログはすべて展開先ルート直下の`logs/`ディレクトリに出力されます。

- **Agent Runnerの実行ログ**: `logs/<repo>/<timestamp>.log`（`<repo>`は対象リポジトリ名、`<timestamp>`は日本時間基準の実行開始時刻）に、issueへのディスパッチ1回ごとに1ファイルとして記録されます。実行中も随時追記されるため、`tail -f logs/<repo>/<timestamp>.log`で進行状況をリアルタイムに確認できます。ダッシュボードの「プロジェクトの並行状況」で異常（実行中プロセスが見つからない等）が疑われる場合の一次切り分けにも使えます。古いログファイルは、`config/projects.yaml`の`log_retention_days`（既定7日）より更新日時が古くなった時点で、次回の実行完了時に自動削除されます。
- **dashboardのログ**: `logs/dashboard.log`にNext.jsサーバー自体の標準出力・標準エラー出力が記録されます。`orchestrator.log`と同様に日次（JST 0時）でローテーションし、`log_retention_days`分保持されます。
- **orchestratorのログ**: `logs/orchestrator.log`に`時刻(JST) [レベル] メッセージ`形式で記録されます。日付単位でローテーションし、`log_retention_days`（既定7日）分保持されます。万一この仕組み自体が動き出す前にクラッシュした場合の記録は、フォールバックとして`logs/orchestrator.stderr.log`に残ります（同様に日次ローテーション）。

## システムの動作仕様（概要）

producer-deskは独自のデータベースを持たず、**GitHub Issuesを正のデータストア**として動作します。詳細設計は[`docs/basic-design.md`](./docs/basic-design.md)を参照してください。ここでは運用者が押さえておくべき挙動の要点のみをまとめます。

- **状態はラベルで管理される**: 各issueには常に1つだけ状態ラベルが付与されます。`status:todo`（未着手）→ `status:in-progress`（作業中）→ `needs-human-decision`（判断待ち）または`status:in-review`（レビュー待ち）→ `status:closed`（完了）という流れで遷移し、いずれのラベル付け替えもAgent Runnerまたはオーケストレータ自身が自動で行います（人間が手動でラベルを付け替える必要は基本的にありません）。
- **5分間隔のポーリング**: オーケストレータは5分ごとに対象リポジトリのissue一覧を取得し、ラベル遷移の検知・判断待ち/レビュー待ちの集約・Slack通知を行います。ダッシュボードから操作した直後は同期的に最新状態へ更新されるため、5分待たずに反映されます。
- **Agent Runnerが自動で行うこと**: ディスパッチされると、Claude Code CLI（`claude -p --dangerously-skip-permissions`）が対象プロジェクトのworktree内でフル自動実行され、調査・実装・テスト・PR作成・ラベルの自己更新までを行います。1プロジェクトにつき同時に実行されるAgent Runnerは1つのみで、複数の指示が重なった場合はプロジェクトごとのキューで順次処理されます。
- **Agent Runnerが自動で行わないこと**: 設計判断が必要と自ら判断した場合は`needs-human-decision`で停止し、人間の承認なしにPRをマージすることはありません。issueの再オープンはproducer-deskの操作範囲外で、再着手させたい場合は人間がGitHub上でreopenする必要があります。issueのクローズ自体は、レビュー承認時にproducer-desk（オーケストレータ）がPRのsquash merge後に明示的に行います（GitHubのPRマージによる自動クローズには依存しません。本プロジェクトのPRは`develop`向けのため、GitHubの`Closes #`による自動クローズが働かないための対処です）。
- **権限・ネットワーク**: 現時点では同一LAN内からのアクセスのみを想定し、アプリケーションレベルの追加認証（Basic認証等）は設けていません。外出先からのアクセスはTailscale経由（`TAILSCALE_IP`）で対応しており、tailnetのネットワーク境界で保護します。Agent Runner自体は`--dangerously-skip-permissions`でworktree内のフル自動実行を許可されています。
- **Agent Runner実行時はユーザー個別のClaude Code設定が適用されない場合があります**: Agent Runnerは`claude -p`によるheadless（非対話）実行のため、対話セッションでは有効な利用者個人の`~/.claude/settings.json`のフック（特に`mcp_tool`タイプの`SessionStart`フック等）やグローバル`CLAUDE.md`の指示が、Agent Runner実行時には適用されない場合があります。確実に反映させたい指示（回答言語等）は、対象プロジェクトリポジトリ自身の`CLAUDE.md`に明記してください（Agent Runnerは対象プロジェクトのworktreeをカレントディレクトリとして起動されるため、そのプロジェクトのCLAUDE.mdは確実に読み込まれます）。

## バックアップ・トラブルシューティング

### DBバックアップ（macOS launchd）

`config/usage.db`（利用量・コスト記録用SQLite）はローカルファイルで自動的にはバックアップされません。`scripts/backup_usage_db.sh` と launchd の per-user LaunchAgent を使って日次バックアップする場合は、以下の手順を行います。

```bash
cp scripts/com.nosetech.producer-desk.backup-usage-db.plist.example \
  ~/Library/LaunchAgents/com.nosetech.producer-desk.backup-usage-db.plist
```

コピー後のファイル内の `/path/to/producer-desk` を、展開先の実際の絶対パスに書き換えます（`ProgramArguments`・`StandardOutPath`・`StandardErrorPath`の3箇所）。

```bash
launchctl load -w ~/Library/LaunchAgents/com.nosetech.producer-desk.backup-usage-db.plist
```

読み込み後は毎日3:00（システムのタイムゾーン設定に従う）に自動実行されます。バックアップ先はデフォルト`~/Backups/producer-desk/`で、環境変数`BACKUP_DEST_DIR`で上書きできます（`launchd`から実行する場合はplistの`EnvironmentVariables`キーで設定します）。保持世代数はデフォルト30日分で、環境変数`BACKUP_RETENTION_DAYS`で上書きできます。

即時実行して動作確認する場合:

```bash
launchctl start com.nosetech.producer-desk.backup-usage-db
```

`logs/backup_usage_db.log`に実行結果が出力され、バックアップ先ディレクトリにタイムスタンプ付きのファイル（例: `usage-20260811-030000.db`）が作成されていることを確認します。

停止する場合:

```bash
launchctl unload ~/Library/LaunchAgents/com.nosetech.producer-desk.backup-usage-db.plist
```

復元する場合は、オーケストレータを停止した状態で、復元したいバックアップファイルを`config/usage.db`に上書きコピーします。

```bash
cp ~/Backups/producer-desk/usage-<timestamp>.db config/usage.db
```

### トラブルシューティング

- **`config/projects.yaml が見つかりません`**: 「初期設定」を実施していません。`config/projects.yaml.example` からコピーして作成してください。
- **`orchestrator/dist/*.whl が見つかりません`**: 配布パッケージ（tarball）が壊れている可能性があります。ダウンロードし直してください。
- **ポートが衝突する**: 環境変数 `ORCHESTRATOR_PORT` / `DASHBOARD_PORT` （LiteLLM Proxyを使っている場合は `LITELLM_PROXY_PORT` も）で別ポートを指定してください。
- **`orchestrator/.venv/bin/orchestrator` コマンドを直接実行しても `config/projects.yaml` が見つからないと言われる**: このコマンドは実行時のカレントディレクトリを展開先ルート（このファイルがある場所）とみなして`config/`・`logs/`を探します。必ず展開先ルートで `./bin/start.sh` 経由で起動し、`orchestrator`コマンドを別ディレクトリから直接実行しないでください。
- **LiteLLM Proxy経由を選んでいるのに、実行結果がClaude Code CLI直利用にフォールバックされたと通知される**: LiteLLM Proxyプロセスが起動していない、または応答しない場合、Agent Runnerはその旨をissueコメントで通知した上で自動的にClaude Code CLI直利用にフォールバックします（自走タスクの進行自体を止めないための挙動で、`needs-human-decision`には遷移しません）。プロジェクト・issueに保存済みの実行手段の設定自体は変更されないため、`./bin/litellm_proxy_start.sh`でLiteLLM Proxyを起動し直せば、次回以降のディスパッチから再びLiteLLM Proxy経由が使われます。

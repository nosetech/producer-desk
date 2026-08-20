---
name: fix-github-issue
description: github issueを対応する
disable-model-invocation: true
---

GitHub issueを分析して対応してください: issue番号 $ARGUMENTS

以下の手順で進めてください。

1. **Issue 詳細の取得**
   - `gh issue view <issue-number>` で issue 詳細を取得

2. **問題の理解**
   - Issue の説明、背景、要件を理解する

3. **関連ファイルの検索**
   - 実装に必要なファイルを特定する
   - docs/にあるドキュメントも修正すべき箇所があるか特定する

3.5. **ダッシュボード（dashboard/以下）の画面に関わるissueの場合**

- CLAUDE.md「画面デザインの実装ルール」に記載のClaude Design URLについて、まず `DesignSync` MCPツール（`get_project` → `list_files` → `get_file`、`projectId` はURLの `/p/<uuid>` 部分）でデザインの実ソース（`ProducerDesk.dc.html`）を直接取得し、対象コンポーネントのスタイルオブジェクト定義（色・余白・border-radius・アニメーション等）をそのまま読み取る（`WebFetch`は認証エラーで使えない）
- `DesignSync` が権限不足等で使えない場合はフォールバックしない。プレビュー画面のクリック操作でのコード選択やズームしての目視推測、チャットへの問い合わせは不正確になりうるため代替にせず、その旨を明記してその場で作業を停止し人間に確認を求める
- テキストの設計文書（docs/design-prompt-dashboard.md等）にはレイアウトの要件のみが書かれており、色やアイコンの指定はデザインそのものにしかないことに注意する
- **対象画面のデザインがまだ存在しない場合**（`list_files` で該当コンポーネントが見つからない等）、自分でレイアウトや配色を創作しない。`DesignSync` にはチャットでデザインを生成させる手段はない（`list_projects`/`get_project`/`list_files`/`get_file`/`create_project`/`finalize_plan`/`write_files`/`delete_files` 等のファイル同期用メソッドのみで、要件を伝えて生成させる操作はできない）ため、`mcp__claude-in-chrome__*` でClaude Designのプロジェクトを開き、チャット欄に要件を入力してデザイン作成を指示する
  - docs/design-prompt-dashboard.md / -diff.md と同じ形式で要件をまとめ、チャットメッセージとして送信する
  - 既存のマスターファイル `ProducerDesk.dc.html` を直接上書きせず、作業ブランチ名を使った新規ファイル（例: `feature/issue-XX-xxx.dc.html`）としてデザインを作成するよう、チャット指示に明記する
  - ここでのブラウザ操作はチャット欄への文字入力のみに限定する。キャンバス上の要素クリックによるコード選択、プレビューのズームスクリーンショットからの目視推測は行わない（CLAUDE.md「画面デザインの実装ルール」参照、値の取得は必ず `DesignSync` 経由で行う）
  - デザイン作成が完了したら（チャットの応答、または `DesignSync` の `list_files` で新規ファイルの存在を確認）、そのファイルを対象に `DesignSync` の `get_file` で実ソースを取得し、実装を進めてよい。人間による承認を待って実装を止める必要はない（コードとデザインは併せてPRレビュー時に確認される）
  - マスターファイル（`ProducerDesk.dc.html`）へのマージは人間がClaude Design上でレビュー・承認した後に行う操作であり、本スキルの範囲では実施しない
- 実装後は `mcp__claude-in-chrome__*` で完成品と（マスターではなく）作業ブランチ名のデザインファイルのプレビューを並べて見た目が一致することを確認する

3.6. **ローカルLLMの補助的活用**

- コード変更そのものを伴わない補助的な作業（コードレビュー支援・デバッグ調査の下調べ・日本語ドキュメント生成）では、必要に応じてローカルLLM（Ollama）を併用してよい（PR #61 / docs/basic-design.md 4章「モデルルーター設定設計」と同じ方針。Agent Runner本体への実装は `orchestrator/orchestrator/agent_runner.py` の `AGENT_RUNNER_LOCAL_LLM_INSTRUCTION` 参照）。モデルの利用可否確認はMCP `ollama-client`でよいが、実際の生成呼び出しは環境変数`$OLLAMA_BENCH_PATH`が指す`ollama-bench`コマンド（オーケストレータが解決済みの絶対パスを子プロセスの環境変数として渡す。`--record --repo <repo> --issue-number <issue番号>`付き）経由でOllama REST APIを直接呼び出す。MCP `mcp__ollama-client__ollama_chat`はトークン数・処理時間メトリクスを返さず`config/usage.db`に利用量を記録できないため使わない（issue #107）
- タスク種別ごとの推奨モデル:
  - コードレビュー支援: `deepseek-coder-v2:16b`
  - デバッグ調査の下調べ: `deepseek-coder-v2:16b`
  - 日本語ドキュメント生成: `gemma2`
  - 上記以外・速度優先の簡易チェック: `qwen2.5-coder:7b`
- 呼び出すかどうか・どのモデルを使うかは状況に応じて自身で判断してよい。ただし、コード変更そのもの（ステップ5の実装）にはローカルLLMの出力をそのまま採用せず、必ず自分自身（Claude Code）が最終的な変更を行う（ローカルLLMはFunction Callingの信頼性に課題があるため）

4. **実装の計画**
   - 実装に必要な手順を分析する
   - 関連するコンポーネント、変更ファイル、テスト方針を確認する
   - プランモードを使わず、スキル内で直接分析を進める
   - 計画内容をまとめてコンソール出力してから次へ進む

5. **コードの実装**
   - feature/\* ブランチで実装を進める
   - ダッシュボードの画面に関わる場合は、実装後に同じブラウザ操作ツールで実装結果とClaude Design（新規作成した場合は作業ブランチ名のファイル）を見比べ、配色・アイコン等の細部が一致することを確認する（3.5参照）

6. **プルリクエスト作成**
   - develop ブランチへのプルリクエストを作成する
   - PR の説明に「Closes #issue-number」を記載する
   - ステップ3.5で作業ブランチ名の新規デザインファイルを作成した場合は、マスターファイル（`ProducerDesk.dc.html`）へのマージが未承認・未実施である旨をPR説明に明記する
   - **PR 作成完了をコンソールに表示する**

7. **CI 完了待機と確認**

- GitHub Actions による CI が実行される
- CI 完了を待つ（`gh pr view <PR-number> --json statusCheckRollup` で確認）
- **CI が SUCCESS で完了したことを確認してから次へ進む**
- エラーがあれば、原因を調査して修正する

8. **コードレビュー実施**
   - サブエージェント `code-reviewer` を使用して、実装コードの詳細レビューを実施する
   - 重大な問題、改善提案を含むレビュー結果を取得する

9. **レビュー結果をプルリクエストに投稿**
   - 取得したレビュー結果を、以下のコマンドでプルリクエストに投稿する：

   ```bash
   gh pr comment <PR-number> --body "レビュー結果のテキスト"
   ```

   - **コメント投稿完了まで、このステップは完了とはみなさない**
   - コメント投稿後、PR の URL をコンソールに表示する

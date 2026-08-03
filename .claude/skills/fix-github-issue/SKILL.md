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

4. **実装の計画**
   - 実装に必要な手順を分析する
   - 関連するコンポーネント、変更ファイル、テスト方針を確認する
   - プランモードを使わず、スキル内で直接分析を進める
   - 計画内容をまとめてコンソール出力してから次へ進む

5. **コードの実装**
   - feature/\* ブランチで実装を進める

6. **プルリクエスト作成**
   - develop ブランチへのプルリクエストを作成する
   - PR の説明に「Closes #issue-number」を記載する
   - **PR 作成完了をコンソールに表示する**

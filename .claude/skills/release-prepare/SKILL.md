---
name: release-prepare
description: リリースに向けてバージョン番号を更新し、developからmasterへのプルリクエストを作成する
disable-model-invocation: true
---

producer-deskのリリース準備を行ってください: 新バージョン番号 $ARGUMENTS

このSKILLは、GitHub Releasesへのtarball配布（[issue #110](https://github.com/nosetech/producer-desk/issues/110)、`.github/workflows/release.yml`）の前段作業を補助する。**バージョン番号の更新とdevelopからmasterへのプルリクエスト作成までを行い、masterへのマージ・タグ付け（`git tag vX.Y.Z` → push）は行わない。** マージ・タグ付けは人間が最終承認した上で別途行う。

以下の手順で進めてください。

1. **バージョン番号の確認**
   - `$ARGUMENTS` がセマンティックバージョン形式（例: `0.2.0`）であることを確認する。`v`プレフィックスは付けない（タグ名に付与する`v`とは別物）
   - `orchestrator/pyproject.toml`の`[project].version`・`dashboard/package.json`の`version`の現在値を確認し、指定バージョンが現在値より新しいことを確認する

2. **作業ブランチの作成**
   - `develop`ブランチを最新化する（`git fetch origin && git checkout develop && git pull`)
   - `develop`から`release/v$ARGUMENTS`という名前で作業ブランチを作成する（通常の`feature/*`とは異なる命名規則であることに注意。`master`への取り込み専用ブランチであることを明示するため）

3. **バージョン番号の更新**
   - `orchestrator/pyproject.toml`の`[project].version`を`$ARGUMENTS`に更新する
   - `dashboard/package.json`の`version`を`$ARGUMENTS`に更新する（`package-lock.json`のルートバージョンも`npm install --package-lock-only`等で追従させる）
   - 他にバージョン番号を参照している箇所がないか確認する（現時点ではこの2箇所のみの想定）

4. **コミット**
   - 変更をコミットする。コミットメッセージ例: `chore: リリース準備 v$ARGUMENTS`

5. **プルリクエスト作成**
   - `develop`ブランチへではなく、**`master`ブランチへの**プルリクエストを作成する（`gh pr create --base master --head release/v$ARGUMENTS`）
   - PR本文には、更新したバージョン番号と、マージ後の手順を明記する。マージ後の手順には以下を両方含めること
     1. `git tag v$ARGUMENTS` → `git push origin v$ARGUMENTS`でリリースワークフローが起動すること
     2. タグ付け後、`master`を`develop`にマージし、両ブランチの履歴を統合すること（`git checkout develop && git pull && git merge master && git push origin develop`）。`orchestrator/pyproject.toml`・`dashboard/package.json`・`package-lock.json`のバージョン番号でコンフリクトが発生する見込みだが、`master`側（今回リリースしたバージョン）を採用して解消する。この手順を省略すると、`master`と`develop`の履歴が共有祖先を失っていく（あるいは既に失っている場合はさらに乖離する）ため、次回以降のリリースPRで想定外の差分・コンフリクトが再発する（issue #110対応中、v0.1.1リリースPR #135で実際に発生・対応した問題）
   - 通常の`feature/*`→`develop`のワークフロー（`Closes #<issue番号>`の記載等）とは異なる、バージョンリリース専用のPRであるため、対応するissue番号がない場合は`Closes #`の記載は不要（issue #110の対応の一環として作成した場合は、そのissue番号を参照する形でよい）

6. **完了報告**
   - 作成したPRのURLをコンソールに表示する
   - **masterへのマージ・タグ付け（`git tag`・`git push --tags`）、およびタグ付け後の`master`→`develop`マージは人間が行うため、ここでは絶対に実施しない**旨を明記する

## 前提・注意点

- `master`への直接コミットは禁止されている（Inkdropの「Claude Rule」・`CLAUDE.md`のブランチ運用ルール）。本SKILLも例外なくPR経由でのみ`master`を変更する
- タグは`master`上のマージコミットに対して人間が打つ運用とする（マージ前のブランチにタグを打たない）
- 同一バージョンへのリリース再実行は`.github/workflows/release.yml`側が非対応（既存タグへの`gh release create`は失敗する）ため、誤ったバージョン番号で本SKILLを実行した場合はPRをマージせずクローズし、正しいバージョン番号でやり直すこと
- 過去に`master`へ直接コミットでリリースした経緯（v0.1.0）により、`master`と`develop`の履歴が共有祖先を失っていた期間があった。この状態のまま`develop`から`release/*`ブランチを作成すると、GitHubのPR差分・マージ判定が3-way diffの基準点（誤った共通祖先）を使うため、実際には存在しない大量の差分・コンフリクトが表示されることがある（v0.1.1リリースPR #134で発生、#135で`master`起点に作り直して解消）。ステップ5でPR本文に必ず`master`→`develop`マージの手順を含めているのはこの再発防止のため。もし本SKILL実行中に同様の想定外の差分・コンフリクトが出た場合は、`release/v$ARGUMENTS`を`develop`ではなく`master`のtipから作り直すことを検討し、必ず人間に報告すること

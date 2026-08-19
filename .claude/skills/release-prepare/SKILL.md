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
   - PR本文には、更新したバージョン番号と、マージ後の手順（`git tag v$ARGUMENTS` → `git push origin v$ARGUMENTS`でリリースワークフローが起動すること）を明記する
   - 通常の`feature/*`→`develop`のワークフロー（`Closes #<issue番号>`の記載等）とは異なる、バージョンリリース専用のPRであるため、対応するissue番号がない場合は`Closes #`の記載は不要（issue #110の対応の一環として作成した場合は、そのissue番号を参照する形でよい）

6. **完了報告**
   - 作成したPRのURLをコンソールに表示する
   - **masterへのマージ・タグ付け（`git tag`・`git push --tags`）は人間が行うため、ここでは絶対に実施しない**旨を明記する

## 前提・注意点

- `master`への直接コミットは禁止されている（Inkdropの「Claude Rule」・`CLAUDE.md`のブランチ運用ルール）。本SKILLも例外なくPR経由でのみ`master`を変更する
- タグは`master`上のマージコミットに対して人間が打つ運用とする（マージ前のブランチにタグを打たない）
- 同一バージョンへのリリース再実行は`.github/workflows/release.yml`側が非対応（既存タグへの`gh release create`は失敗する）ため、誤ったバージョン番号で本SKILLを実行した場合はPRをマージせずクローズし、正しいバージョン番号でやり直すこと

# Claudeチャットへの追加指示プロンプト: inboxへのキーボードカーソル拡張と`Enter`での主操作（差分）

[design-prompt-dashboard.md](./design-prompt-dashboard.md)でお願いしたダッシュボードデザインに対する**追加の変更依頼**です（issue #339）。[issue一覧のキーボードショートカット（issue #322）](./design-prompt-dashboard-diff-keyboard-shortcuts.md)のカーソル行（`rowCur` / `cardCur`）とショートカットガイド（`kbGuide`）、[inbox（issue #288）](./design-prompt-dashboard-diff-inbox.md)の見た目を引き継いだ差分です。ゼロから作り直す必要はありません。以下を丸ごとコピーし、既存デザインを作成したClaudeとのやり取りに貼り付けてください。

---

## ここからプロンプト

既存のproducer-deskダッシュボードの**プロジェクト別issue一覧画面**のキーボード操作（issue #322で追加した`j`/`k`のカーソル移動とショートカットガイド）を、画面上部の**inboxセクション**にも広げます。あわせて、カーソル行の主な操作を`Enter`で実行できるようにします。そのための見た目を追加してください。それ以外の要素のデザイン・レイアウトはそのまま維持してください。

**重要: 既存のマスターファイル（`ProducerDesk.dc.html` / `ProducerDesk.logic.js` / `ProducerDesk.keyboard.logic.js` / `ProducerDeskInbox.dc.html` 等）は直接上書きせず、`feature/issue-339-inbox-shortcuts.dc.html`（と対の`feature/issue-339-inbox-shortcuts.logic.js`）という新規ファイルとして作成してください。** `.logic.js`は既存のロジック一式（マージ済みのissue #322のカーソル行・ガイドのスタイル`ProducerDesk.keyboard.logic.js`を含む）を読み込んで継承し、差分のスタイルだけを定義する形にしてください（以前の`feature/issue-322-keyboard-shortcuts.logic.js`と同じ方式）。inboxのマークアップが子コンポーネント`ProducerDeskInbox.dc.html`にある場合は、機能用のコピー（例: `feature/issue-339-inbox-shortcuts.inbox.dc.html`）を作って差分を入れてください（`feature/issue-325-decision-card.dashboard.dc.html`と同じ方式）。

### 動作の変更点

| キー | 変更後の動作 |
|---|---|
| `j` / `k` | inboxの項目（登録日時の新しい順）→ issue一覧の行、を**1本の並び**としてカーソルを移す。inboxの最後で`j`を押すとissue一覧の先頭へ、issue一覧の先頭で`k`を押すとinboxの最後へ移る。端では止まる（回り込まない）。inboxを折りたたんでいる間は、inbox項目にはカーソルが行かない |
| `Enter`（新規） | カーソル行の主な操作を実行する。issueの行なら「返信する」、inbox項目なら「計画する」。inbox項目が「依頼中…」「計画を開く」の状態のときや編集中のときは何もしない |

### 追加する内容

1. **inbox行のカーソル表示**
   - カーソルが当たっているinbox行の強調表示を定義してください。issue一覧のカーソル行（`rowCur` / `cardCur`: 青い2pxの枠線）と揃えるかどうかを決めてください。inboxからissue一覧へ`j`で移ったときに、同じ「カーソル」だと分かることを優先してください
   - inbox行の新規追加直後のハイライト（`rowNew`）や、計画バッジ付きの行と重なっても両方の意味が読み取れるようにしてください
   - PC幅とモバイル幅（〜640px）の両方で定義してください
2. **`Enter`で押されるボタンの示し方**
   - カーソル行で`Enter`を押すと実行されるボタン（issue行の「返信する」、inbox行の「計画する」）を、カーソル行にいるときだけ控えめに示すかどうかを決めてください（例: ボタン内に小さな`↵`の`kbd`を出す、何も出さずガイドだけで伝える、など）。示す場合は見た目を定義してください
   - 「依頼中…」「計画を開く」の行では`Enter`が効かないので、効くように見えない表示にしてください
3. **ショートカットガイドへの`Enter`の追加**
   - 既存のガイド（`j` `k` 移動 · `x` 選択 · `Esc` 選択解除 · `h` `l` プロジェクト · `⇧H` `⇧L` フィルタ）に`Enter`を追加してください（例: `↵ 返信／計画`）
   - `Enter`の`kbd`での表記（`↵` / `Enter` 等）と、ガイド内での位置を決めてください
   - 移動（`j` `k`）の対象にinboxが含まれることを、ガイドの文言で示す必要があるか判断してください
4. **モバイル幅（〜640px）ではショートカットガイドを表示しない**（既存どおり）
5. **配色**: 既存の配色トークンを使い、新しい色は増やさない

### 成果物として欲しいもの

1. PC幅のissue一覧画面（inbox展開時）で、次の状態の見本
   - カーソルがinboxの「計画する」が表示されている行にある
   - カーソルがinboxの「依頼中…」または「計画を開く」の行にある
   - カーソルがissue一覧の行にある（inboxにはカーソルが無い）
2. `Enter`を追加した画面下部のショートカットガイド（一括変更バー表示中の状態も含む）
3. モバイル幅（ガイド非表示、inbox行のカーソル表示）
4. ライトモード・ダークモード両方での見た目

既存デザインとのトーン・配色・アイコンの一貫性を保ってください。スタイル値は`.logic.js`側のスタイルオブジェクトとして定義してください。不明点があれば、作成を進める前に質問してください。

## ここまでプロンプト

---

## 補足（プロンプト利用者向けメモ）

- この差分プロンプトは [design-prompt-dashboard.md](./design-prompt-dashboard.md) に対する追加変更であり、単独では使わない。[issue #322の差分](./design-prompt-dashboard-diff-keyboard-shortcuts.md)と[inboxの差分](./design-prompt-dashboard-diff-inbox.md)を前提とする。
- ショートカットの判定仕様（入力中・IME変換中・モーダル表示中・ボタンやリンクにフォーカスがあるときの`Enter`は無効、等）は [basic-design.md](./basic-design.md) 2-4で定義する。
- 作業ブランチ名の新規ファイルとして作成させ、マスターファイル（`ProducerDesk.dc.html`）へのマージは人間がArtifacts上でレビュー・承認した後に行う。
- このプロンプトで作成されたデザイン（`feature/issue-339-inbox-shortcuts.*`）での決定事項:
  - inbox行のカーソルは、issue一覧と同じ青い2pxの枠線（`rowCur` / `cardCur`）にした。
  - `Enter`で押されるボタン（「返信する」「計画する」）は、カーソル行かつPC幅のときだけ右上に小さな`↵`を重ねる。「計画を開く」の行・計画ジョブのバッジだけの行（「依頼中…」扱い）・編集中の行には出さない。
  - ガイドには`↵ 返信／計画`を「移動」の直後に追加した。カーソル行で効くときは強調し、効かない行では薄く（`opacity: .45`）する。

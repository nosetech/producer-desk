# producer-desk dashboard

`producer-desk`（自走型AI開発オーケストレーションシステム）のダッシュボード。Next.jsで実装する。

画面設計は [`docs/design-prompt-dashboard.md`](../docs/design-prompt-dashboard.md) のClaude Designへの委譲プロンプトを元に作成された成果物に準拠する（`CLAUDE.md`「画面デザインの実装ルール」参照）。表示項目・API仕様は [`docs/basic-design.md`](../docs/basic-design.md) 2章に対応する。

## セットアップ

```bash
npm install
cp .env.example .env.local  # ORCHESTRATOR_URL を必要に応じて変更
npm run dev
```

[http://localhost:3000](http://localhost:3000) を開く。オーケストレータ（`orchestrator/`）が `http://127.0.0.1:8787` で起動していないと、判断待ち一覧・活動ログ・承認/却下/指示送信は動作しない。

Next.jsは`15.x`系に固定している。`16.x`系には`/_global-error`ページのプリレンダリングが`TypeError: Cannot read properties of null (reading 'useContext')`で確実に失敗する既知の未解決バグがあり（issue #104参照）、`npm run build && npm run start`による本番相当起動ができないため。`eslint-config-next`が`15.x`ではまだflat config形式のエクスポートを持たないため、`eslint.config.mjs`では`@eslint/eslintrc`の`FlatCompat`で橋渡ししている。

## アーキテクチャ

- ダッシュボード（Next.js）はブラウザから直接オーケストレータのAPIを呼ばない。CORS設定を持たないオーケストレータ内部API（`docs/basic-design.md` 2-2・2-3）へは、Next.jsのRoute Handler（`src/app/api/**/route.ts`）がサーバーサイドでプロキシする。
  - `GET /api/state` → オーケストレータ `GET /api/state`
  - `POST /api/projects/[owner]/[name]/issues/[issueNumber]/instruct` → オーケストレータの指示出しAPI
  - `POST /api/projects/[owner]/[name]/issues` → オーケストレータの新規issue作成API
  - `GET /api/projects` → `config/projects.yaml`（オーケストレータと共有する設定ファイル）を直接読み、対象リポジトリ一覧を返す
- 利用量／リミット表示は、現時点でオーケストレータ側にデータ取得の仕組みが無いため（`docs/basic-design.md` 2-2参照）、UIのみ実装し仮データを表示する。

## デプロイ

MVPでは同一LAN内からのアクセスのみを前提とし、LANインターフェースのIPにのみbindする（`docs/basic-design.md` 6-2参照）。

```bash
LAN_IP=<自機のLAN IP> npm run start:lan
```

オーケストレータの内部APIはこのプロセスから同一マシン上でサーバーサイドに呼び出すのみで、ブラウザから直接到達させる必要が無いため、`127.0.0.1`（既定値）から変更しなくてよい。

外出先からのTailscale経由アクセス対応（`npm run start:tailscale`、`TAILSCALE_IP` 環境変数）は将来拡張issue（#29）で対応する。

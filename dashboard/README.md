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

## アーキテクチャ

- ダッシュボード（Next.js）はブラウザから直接オーケストレータのAPIを呼ばない。CORS設定を持たないオーケストレータ内部API（`docs/basic-design.md` 2-2・2-3）へは、Next.jsのRoute Handler（`src/app/api/**/route.ts`）がサーバーサイドでプロキシする。
  - `GET /api/state` → オーケストレータ `GET /api/state`
  - `POST /api/projects/[owner]/[name]/issues/[issueNumber]/instruct` → オーケストレータの指示出しAPI
  - `POST /api/projects/[owner]/[name]/issues` → オーケストレータの新規issue作成API
  - `GET /api/projects` → `config/projects.yaml`（オーケストレータと共有する設定ファイル）を直接読み、対象リポジトリ一覧を返す
- 利用量／リミット表示は、現時点でオーケストレータ側にデータ取得の仕組みが無いため（`docs/basic-design.md` 2-2参照）、UIのみ実装し仮データを表示する。

## デプロイ

Tailscale経由でのみアクセス可能にするため、`next start --hostname <tailscale-ip>` で起動する（`npm run start:tailscale`、`TAILSCALE_IP` 環境変数）。`docs/basic-design.md` 6-2参照。

// dashboard（Next.js）のプロセス名を ps で判別できる固有名にする（issue #332）。
// `NODE_OPTIONS="--require <このファイル>"` で事前読み込みさせ、環境変数
// PROCESS_TITLE が空でない場合のみ process.title を設定する。
//
// Next.js は起動後に `process.title = "next-server (v...)"` を固定で代入するため、
// setter を無効化してその後続の代入による上書きを防ぐ。NODE_OPTIONS は子プロセス
// （next-render-worker 等）にも継承されるため、それらも同じ名前になる。
//
// プロセス名は人間が ps で見分けるためだけのもの。停止は従来どおりPIDファイル
// （bin/*_stop.sh）・記録したPGID（bin/dev_instance.sh）で行う。
"use strict";

const title = process.env.PROCESS_TITLE;
if (title) {
  process.title = title;
  Object.defineProperty(process, "title", {
    get: () => title,
    set: () => {},
    configurable: true,
  });
}

"use client";

import { useEffect, useRef } from "react";
import {
  resolveIssueListAction,
  shouldIgnoreShortcut,
  type IssueListAction,
} from "./shortcuts";

// ポップオーバー（個別編集・一括変更・MetaFilterのドロップダウン）も`role="dialog"`のため、
// 開いている間は画面内ショートカットを受け付けず、そちらの`Esc`（閉じる）を優先する。
const MODAL_SELECTOR =
  '[role="dialog"], [aria-modal="true"], [role="alertdialog"]';

/**
 * issue一覧画面内のショートカット（issue #322）を window の keydown で受け付ける。
 * `onAction`は処理した場合にtrueを返す（trueのときだけ既定動作を止める）。
 * `disabled`の間（返信バー表示中など）は何もしない。
 */
export function useIssueListShortcuts(
  onAction: (action: IssueListAction) => boolean,
  disabled = false,
) {
  // 描画ごとに変わるハンドラを、リスナーを付け直さずに最新のものへ差し替える。
  const handlerRef = useRef(onAction);
  handlerRef.current = onAction;

  useEffect(() => {
    if (disabled) return;
    function onKeyDown(e: KeyboardEvent) {
      const modalOpen = document.querySelector(MODAL_SELECTOR) !== null;
      const action = resolveIssueListAction(e.key, e.shiftKey);
      if (!action) return;
      // Shiftは`H` / `L`（フィルタ切替）にだけ必須とし、それ以外では無視する（CapsLock中の
      // `H`等で誤ってフィルタが切り替わらないようにする）。
      const isFilter = action === "prevFilter" || action === "nextFilter";
      if (isFilter !== (e.shiftKey === true)) return;
      // `j` / `k`だけ押しっぱなしでの連続移動を許可する。
      const allowRepeat = action === "cursorDown" || action === "cursorUp";
      if (
        shouldIgnoreShortcut(e, modalOpen, {
          allowShift: isFilter,
          allowRepeat,
        })
      ) {
        return;
      }
      if (handlerRef.current(action)) e.preventDefault();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [disabled]);
}

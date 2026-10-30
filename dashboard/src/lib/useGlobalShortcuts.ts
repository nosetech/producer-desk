"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  isSameScreen,
  resolveShortcutHref,
  shouldIgnoreShortcut,
} from "./shortcuts";

const MODAL_SELECTOR = '[role="dialog"], [aria-modal="true"]';

/** 画面遷移ショートカット（d / i / p）を window の keydown で受け付ける。 */
export function useGlobalShortcuts() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const modalOpen = document.querySelector(MODAL_SELECTOR) !== null;
      if (shouldIgnoreShortcut(e, modalOpen)) return;
      const href = resolveShortcutHref(e.key);
      if (!href || isSameScreen(pathname, href)) return;
      e.preventDefault();
      router.push(href);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [router, pathname]);
}

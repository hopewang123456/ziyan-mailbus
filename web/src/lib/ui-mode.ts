/** Cockpit ↔ legacy Dashboard UI mode (same APIs). */

const KEY = "mailbus.ui.mode";

export type UiMode = "cockpit" | "legacy";

export function getUiMode(): UiMode {
  try {
    const q = new URLSearchParams(window.location.search).get("ui");
    if (q === "legacy" || q === "cockpit") return q;
  } catch {
    /* ignore */
  }
  const v = localStorage.getItem(KEY);
  return v === "legacy" ? "legacy" : "cockpit";
}

export function setUiMode(mode: UiMode) {
  localStorage.setItem(KEY, mode);
}

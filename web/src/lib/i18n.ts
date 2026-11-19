const KEY = "mailbus.lang";

export type Lang = "zh" | "en";

export function getLang(): Lang {
  const value = localStorage.getItem(KEY);
  return value === "en" ? "en" : "zh";
}

export function setLang(lang: Lang) {
  localStorage.setItem(KEY, lang);
}

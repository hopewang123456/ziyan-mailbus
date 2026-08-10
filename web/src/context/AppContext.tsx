import {
  createContext,
  useContext,
  useMemo,
  useState,
  useEffect,
  type ReactNode,
} from "react";
import { getToken, setToken as persistToken } from "../lib/api";
import { getLang, setLang as persistLang, type Lang } from "../lib/i18n";
import { getUiMode, setUiMode as persistUiMode, type UiMode } from "../lib/ui-mode";

type AppState = {
  token: string;
  setToken: (token: string) => void;
  lang: Lang;
  setLang: (lang: Lang) => void;
  uiMode: UiMode;
  setUiMode: (mode: UiMode) => void;
};

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState(getToken());
  const [lang, setLangState] = useState<Lang>(getLang());
  const [uiMode, setUiModeState] = useState<UiMode>(getUiMode());

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === "mailbus_api_token") setTokenState(getToken());
      if (e.key === "mailbus.lang") setLangState(getLang());
      if (e.key === "mailbus.uiMode") setUiModeState(getUiMode());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const value = useMemo<AppState>(
    () => ({
      token,
      setToken: (t: string) => {
        persistToken(t);
        setTokenState(t);
      },
      lang,
      setLang: (l: Lang) => {
        persistLang(l);
        setLangState(l);
      },
      uiMode,
      setUiMode: (m: UiMode) => {
        persistUiMode(m);
        setUiModeState(m);
      },
    }),
    [token, lang, uiMode],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppContext(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAppContext requires AppProvider");
  return ctx;
}

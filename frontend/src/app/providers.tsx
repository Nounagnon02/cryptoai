"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";

// ─── Theme Context ───────────────────────────────────────────

type Theme = "dark" | "light";

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "dark",
  toggleTheme: () => {},
});

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}

function ThemeProviderWrapper({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    // Lire le thème sauvegardé au montage
    const stored = localStorage.getItem("cryptoai-theme") as Theme | null;
    if (stored === "light" || stored === "dark") {
      setTheme(stored);
      document.documentElement.classList.toggle("light", stored === "light");
    }
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      localStorage.setItem("cryptoai-theme", next);
      document.documentElement.classList.toggle("light", next === "light");
      return next;
    });
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

// ─── Main Providers ──────────────────────────────────────────

export default function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProviderWrapper>{children}</ThemeProviderWrapper>
    </QueryClientProvider>
  );
}

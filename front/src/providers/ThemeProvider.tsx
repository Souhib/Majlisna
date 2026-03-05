import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react"

type Theme = "light" | "dark" | "system"

interface ThemeContextValue {
  theme: Theme
  setTheme: (theme: Theme) => void
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)

const THEME_KEY = "ipg-theme"

interface ThemeProviderProps {
  children: ReactNode
  defaultTheme?: Theme
}

export function ThemeProvider({ children, defaultTheme = "system" }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(() => {
    const stored = localStorage.getItem(THEME_KEY) as Theme | null
    return stored || defaultTheme
  })

  const applyTheme = useCallback((t: Theme) => {
    const root = document.documentElement
    root.classList.remove("light", "dark")

    if (t === "system") {
      const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches
      root.classList.add(systemDark ? "dark" : "light")
    } else {
      root.classList.add(t)
    }
  }, [])

  useEffect(() => {
    applyTheme(theme)
  }, [theme, applyTheme])

  // Listen for system theme changes
  useEffect(() => {
    if (theme !== "system") return
    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    const handler = () => applyTheme("system")
    mq.addEventListener("change", handler)
    return () => mq.removeEventListener("change", handler)
  }, [theme, applyTheme])

  const setTheme = useCallback((t: Theme) => {
    localStorage.setItem(THEME_KEY, t)
    setThemeState(t)
  }, [])

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider")
  }
  return context
}

"use client"

import * as React from "react"
import {
  applyAppearanceTheme,
  loadAppearancePreferences,
} from "@/lib/api/settings"

export function ThemeInitializer() {
  React.useEffect(() => {
    const syncTheme = () => {
      const prefs = loadAppearancePreferences()
      applyAppearanceTheme(prefs.theme)
    }

    syncTheme()

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)")
    const handleMediaChange = () => {
      if (loadAppearancePreferences().theme === "system") {
        syncTheme()
      }
    }

    window.addEventListener("appearance-preferences-updated", syncTheme)
    window.addEventListener("storage", syncTheme)
    mediaQuery.addEventListener("change", handleMediaChange)

    return () => {
      window.removeEventListener("appearance-preferences-updated", syncTheme)
      window.removeEventListener("storage", syncTheme)
      mediaQuery.removeEventListener("change", handleMediaChange)
    }
  }, [])

  return null
}

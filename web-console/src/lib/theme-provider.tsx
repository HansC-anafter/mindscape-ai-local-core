'use client'

import { ThemeProvider as NextThemesProvider } from 'next-themes'
import { type ThemeProviderProps } from 'next-themes'
import { useEffect } from 'react'
import { useTheme } from 'next-themes'
import { applyThemePreset } from './theme-preset'

export function ThemeProvider({ children, ...props }: ThemeProviderProps) {
  return (
    <NextThemesProvider {...props}>
      <ThemePresetSync>{children}</ThemePresetSync>
    </NextThemesProvider>
  )
}

function ThemePresetSync({ children }: { children: React.ReactNode }) {
  const { resolvedTheme } = useTheme()

  useEffect(() => {
    if (resolvedTheme) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          applyThemePreset(resolvedTheme as 'light' | 'dark')
        })
      })
    } else {
      applyThemePreset()
    }
  }, [resolvedTheme])

  useEffect(() => {
    const initializePreset = () => {
      requestAnimationFrame(() => {
        if (resolvedTheme) {
          applyThemePreset(resolvedTheme as 'light' | 'dark')
        } else {
          applyThemePreset()
        }
      })
    }

    const timeoutId = setTimeout(initializePreset, 100)

    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'theme-preset') {
        if (resolvedTheme) {
          applyThemePreset(resolvedTheme as 'light' | 'dark')
        } else {
          applyThemePreset()
        }
      }
    }

    const handlePresetChange = () => {
      if (resolvedTheme) {
        applyThemePreset(resolvedTheme as 'light' | 'dark')
      } else {
        applyThemePreset()
      }
    }

    window.addEventListener('storage', handleStorageChange)
    window.addEventListener('theme-preset-changed', handlePresetChange)

    return () => {
      clearTimeout(timeoutId)
      window.removeEventListener('storage', handleStorageChange)
      window.removeEventListener('theme-preset-changed', handlePresetChange)
    }
  }, [resolvedTheme])

  return <>{children}</>
}

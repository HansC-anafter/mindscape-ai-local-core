'use client'

import { ThemeProvider as NextThemesProvider } from 'next-themes'
import { type ThemeProviderProps } from 'next-themes/dist/types'
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
    // Apply theme preset when theme changes
    // Use requestAnimationFrame to ensure DOM has been updated by next-themes
    console.log('[Theme Provider] Theme changed to:', resolvedTheme)

    if (resolvedTheme) {
      // Use requestAnimationFrame to ensure next-themes has updated the DOM
      requestAnimationFrame(() => {
        // Double-check: wait one more frame to be absolutely sure
        requestAnimationFrame(() => {
          // Pass the resolvedTheme directly to avoid timing issues
          applyThemePreset(resolvedTheme as 'light' | 'dark')
        })
      })
    } else {
      // Fallback: if resolvedTheme is not available, use DOM detection
      applyThemePreset()
    }
  }, [resolvedTheme])

  useEffect(() => {
    // Apply preset on mount - wait for next-themes to resolve theme
    // Use requestAnimationFrame to ensure next-themes has initialized
    const initializePreset = () => {
      requestAnimationFrame(() => {
        if (resolvedTheme) {
          console.log('[Theme Provider] Initializing theme preset with resolved theme:', resolvedTheme)
          applyThemePreset(resolvedTheme as 'light' | 'dark')
        } else {
          // Fallback: if resolvedTheme not available yet, use DOM detection
          console.log('[Theme Provider] Initializing theme preset (fallback to DOM detection)')
          applyThemePreset()
        }
      })
    }

    // Wait a bit for next-themes to initialize
    const timeoutId = setTimeout(initializePreset, 100)

    // Listen for storage changes (when preset changes in another tab)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'theme-preset') {
        console.log('[Theme Provider] Storage changed, applying preset')
        if (resolvedTheme) {
          applyThemePreset(resolvedTheme as 'light' | 'dark')
        } else {
          applyThemePreset()
        }
      }
    }

    // Listen for custom event (when preset changes in current tab)
    const handlePresetChange = () => {
      console.log('[Theme Provider] Theme preset changed event received')
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
  }, [resolvedTheme]) // Add resolvedTheme as dependency to re-initialize when it becomes available

  return <>{children}</>
}


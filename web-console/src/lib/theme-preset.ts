/**
 * Theme preset management utilities
 * Supports multiple visual style presets for light mode
 */

export type ThemePreset = 'default' | 'warm'

const THEME_PRESET_KEY = 'theme-preset'

/**
 * Get current theme preset from localStorage
 */
export function getThemePreset(): ThemePreset {
  if (typeof window === 'undefined') return 'default'
  const preset = localStorage.getItem(THEME_PRESET_KEY) as ThemePreset
  return preset || 'default'
}

/**
 * Set theme preset and apply to document
 */
export function setThemePreset(preset: ThemePreset): void {
  if (typeof window === 'undefined') return

  localStorage.setItem(THEME_PRESET_KEY, preset)

  // Apply preset immediately
  applyThemePreset()

  // Dispatch custom event to notify other components
  window.dispatchEvent(new CustomEvent('theme-preset-changed', { detail: { preset } }))
}

/**
 * Apply theme preset based on current theme mode
 * @param themeMode Optional theme mode ('light' | 'dark'). If not provided, will detect from DOM.
 */
export function applyThemePreset(themeMode?: 'light' | 'dark'): void {
  if (typeof window === 'undefined') return

  const preset = getThemePreset()
  const html = document.documentElement

  // Determine if dark mode: use provided themeMode if available, otherwise check DOM
  let isDark: boolean
  if (themeMode !== undefined) {
    isDark = themeMode === 'dark'
  } else {
    isDark = html.classList.contains('dark')
  }

  // Remove all preset classes
  html.classList.remove('theme-warm', 'theme-default')

  // Only apply preset in light mode
  if (!isDark) {
    if (preset === 'warm') {
      html.classList.add('theme-warm')
    }
    // default preset doesn't need a class, uses :root styles
  }

}

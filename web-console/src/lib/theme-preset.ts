export type ThemePreset = 'default' | 'warm'

const THEME_PRESET_KEY = 'theme-preset'

export function getThemePreset(): ThemePreset {
  if (typeof window === 'undefined') return 'default'
  const preset = localStorage.getItem(THEME_PRESET_KEY) as ThemePreset
  return preset || 'default'
}

export function setThemePreset(preset: ThemePreset): void {
  if (typeof window === 'undefined') return

  localStorage.setItem(THEME_PRESET_KEY, preset)

  applyThemePreset()

  window.dispatchEvent(new CustomEvent('theme-preset-changed', { detail: { preset } }))
}

export function applyThemePreset(themeMode?: 'light' | 'dark'): void {
  if (typeof window === 'undefined') return

  const preset = getThemePreset()
  const html = document.documentElement

  let isDark: boolean
  if (themeMode !== undefined) {
    isDark = themeMode === 'dark'
  } else {
    isDark = html.classList.contains('dark')
  }

  html.classList.remove('theme-warm', 'theme-default')

  if (!isDark) {
    if (preset === 'warm') {
      html.classList.add('theme-warm')
    }
  }

}

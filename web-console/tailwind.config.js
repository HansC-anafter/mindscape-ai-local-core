/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // CSS Variable-based colors that respect theme presets
        surface: 'var(--color-surface)',
        'surface-secondary': 'var(--color-surface-secondary)',
        'surface-accent': 'var(--color-surface-accent)',
        tertiary: 'var(--color-tertiary)',
        'tertiary-dark': 'var(--color-tertiary-dark)',
        accent: 'var(--color-accent)',
        'accent-10': 'var(--color-accent-10)',
        border: 'var(--color-border)',
        'text-primary': 'var(--color-text-primary)',
        'text-secondary': 'var(--color-text-secondary)',
        'text-tertiary': 'var(--color-text-tertiary)',
        // Warm Day Mode Design System Colors (direct values for reference)
        'ds-background': '#F7EFE0',
        'ds-primary': '#864809',
        'ds-secondary': '#FCF6E8',
        'ds-tertiary': '#EADBBE',
        'ds-tertiary-dark': '#B8A57F',
        'ds-text-primary': '#1A1818',
        'ds-text-secondary': '#7F7F7F',
        'ds-white': '#FFFFFF',
      },
      backgroundColor: {
        'surface': 'var(--color-surface)',
        'surface-secondary': 'var(--color-surface-secondary)',
        'surface-accent': 'var(--color-surface-accent)',
        'tertiary': 'var(--color-tertiary)',
        'tertiary-dark': 'var(--color-tertiary-dark)',
        'accent': 'var(--color-accent)',
        'accent-10': 'var(--color-accent-10)',
        'message-user': 'var(--bg-message-user)',
        'message-assistant': 'var(--bg-message-assistant)',
        'suggestion': 'var(--bg-suggestion)',
        'intent': 'var(--bg-intent)',
        'row': 'var(--bg-row)',
        'row-hover': 'var(--bg-row-hover)',
      },
      textColor: {
        'primary': 'var(--color-text-primary)',
        'secondary': 'var(--color-text-secondary)',
        'tertiary': 'var(--color-text-tertiary)',
        'accent': 'var(--color-accent)',
      },
      borderColor: {
        'default': 'var(--color-border)',
        'accent': 'var(--color-accent)',
      },
      placeholderColor: {
        'tertiary': 'var(--color-text-tertiary)',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        'ds': '12px',
        'ds-lg': '16px',
      },
      boxShadow: {
        'message': 'var(--elevation-message)',
        'card': 'var(--elevation-card)',
      },
    },
  },
  plugins: [],
}

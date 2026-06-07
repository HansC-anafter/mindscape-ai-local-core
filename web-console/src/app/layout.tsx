import type { Metadata } from 'next'
import './globals.css'
import { LocaleProvider } from '../lib/i18n'
import { ThemeProvider } from '../lib/theme-provider'
import { KeyboardShortcutProvider } from '../lib/keyboard-shortcuts/KeyboardShortcutProvider'

export const metadata: Metadata = {
  title: 'Mindscape AI - Personal Agent Console',
  description: 'Your personal AI team workspace powered by mindscape',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-TW" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <LocaleProvider>
            <KeyboardShortcutProvider>
              {children}
            </KeyboardShortcutProvider>
          </LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}

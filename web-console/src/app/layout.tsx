import type { Metadata } from 'next'
import './globals.css'
import { LOCALE_DIRECTION, LocaleProvider } from '../lib/i18n'
import { getServerLocaleSnapshot } from '../lib/i18n/server'
import { ThemeProvider } from '../lib/theme-provider'
import { KeyboardShortcutProvider } from '../lib/keyboard-shortcuts'

export const metadata: Metadata = {
  title: 'Mindscape AI - Personal Agent Console',
  description: 'Your personal AI team workspace powered by mindscape',
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const localeSnapshot = await getServerLocaleSnapshot()

  return (
    <html
      lang={localeSnapshot.locale}
      dir={LOCALE_DIRECTION[localeSnapshot.locale]}
      suppressHydrationWarning
    >
      <body suppressHydrationWarning>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <LocaleProvider initialSnapshot={localeSnapshot}>
            <KeyboardShortcutProvider>
              {children}
            </KeyboardShortcutProvider>
          </LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}

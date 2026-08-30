import { Analytics } from '@vercel/analytics/next'
import { Space_Grotesk, JetBrains_Mono } from 'next/font/google'
import type { Metadata, Viewport } from 'next'
import './globals.css'
import Sidebar from '@/components/sidebar'

const space = Space_Grotesk({ subsets: ['latin'], variable: '--font-space' })
const jet = JetBrains_Mono({ subsets: ['latin'], variable: '--font-jetbrains' })

export const metadata: Metadata = {
  title: 'RedBlue | Payment Defense Twin',
  description: 'Closed-loop adversarial payment defense lab - Mastercard Innovation Challenge 2026',
}

export const viewport: Viewport = {
  colorScheme: 'light',
  themeColor: '#ffffff',
  userScalable: false,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${space.variable} ${jet.variable}`}>
      <body style={{ margin: 0, background: '#f8f9fa', fontFamily: "'Space Grotesk', sans-serif" }}>
        <Sidebar />
        <main style={{ marginLeft: 240, minHeight: '100vh', padding: '0 0 40px' }}>
          {children}
        </main>
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}

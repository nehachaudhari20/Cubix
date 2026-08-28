import { Analytics } from '@vercel/analytics/next'; import { Space_Grotesk, JetBrains_Mono } from 'next/font/google'; import type {Metadata,Viewport} from 'next'; import './globals.css';
const space=Space_Grotesk({subsets:['latin'],variable:'--font-space'}); const jet=JetBrains_Mono({subsets:['latin'],variable:'--font-jetbrains'});
export const metadata:Metadata={title:'Payment Defense Twin | Command Center',description:'Continuous red-team and blue-team payment fraud simulation command center'};
export const viewport:Viewport={colorScheme:'light',themeColor:'#ffffff',userScalable:false};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en" className={`${space.variable} ${jet.variable}`}><body>{children}{process.env.NODE_ENV==='production'&&<Analytics/>}</body></html>}

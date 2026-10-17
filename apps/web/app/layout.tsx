import type {Metadata} from "next";
import {Inter, Inter_Tight, Onest} from "next/font/google";
import {Providers} from "@/components/providers";
import "@/styles/globals.css";

const inter = Inter({subsets: ["latin"], variable: "--font-body"});
const numbers = Inter_Tight({subsets: ["latin"], variable: "--font-numbers"});
const onest = Onest({subsets: ["latin"], variable: "--font-onest"});
export const metadata: Metadata = {
  title: "Whistles",
  description: "Evidence-led listening intelligence",
  icons: {icon: [{url: "/brand/mark.svg", type: "image/svg+xml"}]},
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="en" suppressHydrationWarning><body suppressHydrationWarning className={`${inter.variable} ${numbers.variable} ${onest.variable} font-sans`}><Providers>{children}</Providers></body></html>;
}

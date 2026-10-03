import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Archivo, Martian_Mono } from "next/font/google";
import "./tokens.css";
import "./globals.css";
import "@/styles/tokens.css";
import "@/styles/base.css";

// DESIGN.md, Type. Both under the SIL Open Font License 1.1; next/font self-hosts them at build time.
const archivo = Archivo({
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["wdth"],
  variable: "--font-archivo",
  display: "swap",
});

const martian = Martian_Mono({
  subsets: ["latin"],
  axes: ["wdth"],
  variable: "--font-martian",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Planet Hunter",
  description: "A monitor of the search for planets in NASA's TESS data: each star's real light curve, the dips the search finds, and why each was kept or turned down.",
};

export const viewport: Viewport = {
  themeColor: "#fafaf7",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

const THEME_BOOT = `try{if(localStorage.getItem("ph-theme")==="night")document.documentElement.dataset.theme="night"}catch(e){}`;

// Geist stays loaded only for the retired pages (events, sky, lab) until they are removed.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable} ${archivo.variable} ${martian.variable}`} suppressHydrationWarning>
      <head>
        {/* Day is the default; a Night choice made with the top bar's switch is applied before first paint. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}

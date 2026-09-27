import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Martian_Mono, Newsreader } from "next/font/google";
import "./tokens.css";
import "./globals.css";
import "@/styles/tokens.css";
import "@/styles/base.css";

// DESIGN.md, Type. Both under the SIL Open Font License 1.1; next/font self-hosts them at build time.
const newsreader = Newsreader({
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["opsz"],
  variable: "--font-newsreader",
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
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ede8dc" },
    { media: "(prefers-color-scheme: dark)", color: "#12110e" },
  ],
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

// Geist stays loaded only for the retired pages (events, sky, lab) until they are removed.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable} ${newsreader.variable} ${martian.variable}`}>
      <body>{children}</body>
    </html>
  );
}

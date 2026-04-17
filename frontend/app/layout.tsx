import type { Metadata } from "next";
import Link from "next/link";
import { Fraunces, Manrope } from "next/font/google";
import type { ReactNode } from "react";

import "./globals.css";

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-serif",
});

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "Academic Tour Guide",
  description: "KOF opportunity scoring and concierge outreach dashboard.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${fraunces.variable} ${manrope.variable}`}>
        <div className="app-shell">
          <header className="topbar">
            <div className="brand">
              <span className="brand-title">Academic Tour Guide</span>
              <span className="brand-subtitle">
                Scrape the European seminar circuit, score invitation windows, and give KOF a concierge-grade outreach desk.
              </span>
            </div>
            <nav className="nav-links">
              <Link href="/">Daily Catch</Link>
              <Link href="/seminar-admin">Seminar Admin</Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}

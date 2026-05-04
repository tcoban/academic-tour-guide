import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
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
  title: "Roadshow",
  description: "KOF-first academic tour concierge and opportunity desk.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${fraunces.variable} ${manrope.variable}`}>
        <div className="app-shell">
          <header className="topbar">
            <div className="brand">
              <span className="brand-title">Roadshow</span>
              <span className="brand-subtitle">
                Scout the European seminar circuit, model tour legs, and give KOF a concierge-grade Roadshow desk.
              </span>
            </div>
            <nav className="nav-links">
              <Link href="/">Start</Link>
              <Link href="/opportunities">Opportunities</Link>
              <Link href="/calendar">Calendar</Link>
              <Link href="/review">Evidence</Link>
              <Link href="/drafts">Drafts</Link>
              <details className="nav-tools">
                <summary>Settings</summary>
                <div className="nav-menu">
                  <Link href="/seminar-admin">KOF Slots</Link>
                  <Link href="/wishlist">Wishlist</Link>
                  <Link href="/tour-assemblies">Tour Assemblies</Link>
                  <Link href="/tour-legs">Tour Legs</Link>
                  <Link href={"/business-cases" as Route}>Business Case Audit</Link>
                  <Link href="/source-health">Data Sources</Link>
                  <Link href="/runbook">Runbook</Link>
                </div>
              </details>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Basketball Model — Tips Board",
  description: "ML + Spread + Totals ensemble picks for NBA and EuroLeague",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (<html lang="en"><body>{children}</body></html>);
}

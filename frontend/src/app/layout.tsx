import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Sidebar from "@/components/Sidebar";
import Providers from "./providers";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "CryptoAI — Trading Platform",
  description:
    "Plateforme de trading crypto autonome pilotée par IA — Niveau Hedge Fund",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr" className="dark" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans`}>
        <Providers>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 ml-64 p-6 lg:p-8 max-w-7xl">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}

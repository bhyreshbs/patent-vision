import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PatentVision AI",
  description: "Turn product photographs into clean black-and-white patent-style outline drawings.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}

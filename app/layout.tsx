import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Starter CX | AI Support Console",
  description: "A secure Gemini-powered synthetic telecom customer-support demo.",
  applicationName: "Starter CX",
  manifest: "/manifest.json",
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: "Starter CX" }
};

export const viewport: Viewport = {
  themeColor: "#10151f",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

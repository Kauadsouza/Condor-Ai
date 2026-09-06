import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Condor Cloud",
  description: "A mesma mente do Condor no celular e no PC.",
  applicationName: "Condor Cloud",
  manifest: "/manifest.webmanifest",
  icons: [{ rel: "icon", url: "/condor.svg" }],
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#02050b",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pt-BR"><body>{children}</body></html>;
}

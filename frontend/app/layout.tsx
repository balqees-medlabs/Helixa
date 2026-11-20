import type { Metadata } from "next";

import { Providers } from "@/app/providers";
import { getDirection, getLocale } from "@/lib/i18n/dir";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "Helixa | Medlabs Genomics",
  description: "Medlabs Genomics sample workflow and turnaround portal.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang={getLocale()} dir={getDirection()}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

import { ThemeProvider } from "@/components/theme-provider";
import type { Metadata } from "next";
import { Header } from "../components/Header";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Snake",
  description: "Snake Bootcamp Project",
};

// basic root layout setup
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head />
      <body>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <header className="sticky top-0 z-50">
            <Header />
          </header>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}

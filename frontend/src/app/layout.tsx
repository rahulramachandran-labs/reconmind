import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { SiteNav } from "@/components/site-nav";
import { UserMenu } from "@/components/user-menu";
import "./globals.css";

const sans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ReconMind",
  description:
    "Multi-agent, RAG-powered incident copilot for data pipelines: key drift, duplicate submissions, schema drift and volume anomalies.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`dark ${sans.variable} ${mono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <SiteNav user={<UserMenu />} />
        {children}
      </body>
    </html>
  );
}

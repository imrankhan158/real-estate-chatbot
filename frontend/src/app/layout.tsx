import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Real Estate AI Chatbot – DarGlobal & Wasalt",
  description:
    "AI-powered property search across DarGlobal luxury listings and Wasalt Saudi real estate marketplace.",
  keywords: "real estate, Dubai, Saudi Arabia, DarGlobal, Wasalt, property, AI chatbot",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-[#0f0f0f] text-gray-100 antialiased">{children}</body>
    </html>
  );
}

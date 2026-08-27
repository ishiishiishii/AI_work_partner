import type { Metadata } from "next";
import { Orbitron } from "next/font/google";
import { AppNav } from "@/components/AppNav";
import { InitialPlanGenerationProvider } from "@/lib/initialPlanGenerationContext";
import { QuickAddPlanProvider } from "@/lib/quickAddPlanContext";
import { RepProvider } from "@/lib/repContext";
import { RouteBatchPlanProvider } from "@/lib/routeBatchPlanContext";
import "./globals.css";

const orbitron = Orbitron({
  subsets: ["latin"],
  weight: ["500", "700", "900"],
  variable: "--font-orbitron",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AI Work Partner",
  description: "FastAPI + Next.js + Supabase development environment",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja" className={orbitron.variable}>
      <body>
        <RepProvider>
          <QuickAddPlanProvider>
            <InitialPlanGenerationProvider>
              <RouteBatchPlanProvider>
                <AppNav />
                {children}
              </RouteBatchPlanProvider>
            </InitialPlanGenerationProvider>
          </QuickAddPlanProvider>
        </RepProvider>
      </body>
    </html>
  );
}

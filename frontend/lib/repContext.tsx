"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { mockSalesReps } from "@/lib/mockData";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import type { SalesRep } from "@/types";

type RepContextValue = {
  selectedRep: SalesRep | null;
  isAuthLoading: boolean;
  signOut: () => Promise<void>;
};

const RepContext = createContext<RepContextValue | null>(null);

// ログインしていなくても見られる画面
const PUBLIC_PATHS = ["/login"];

export function RepProvider({ children }: { children: React.ReactNode }) {
  const [repId, setRepId] = useState<number | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const supabase = getSupabaseBrowserClient();
    if (!supabase) {
      setIsAuthLoading(false);
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      setRepId((data.session?.user.app_metadata.rep_id as number | undefined) ?? null);
      setIsAuthLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setRepId((session?.user.app_metadata.rep_id as number | undefined) ?? null);
    });

    return () => listener.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (isAuthLoading) return;
    const isPublicPath = PUBLIC_PATHS.includes(pathname);
    if (repId === null && !isPublicPath) {
      router.replace("/login");
    }
  }, [isAuthLoading, repId, pathname, router]);

  const selectedRep = repId !== null ? (mockSalesReps.find((rep) => rep.rep_id === repId) ?? null) : null;

  async function signOut() {
    const supabase = getSupabaseBrowserClient();
    await supabase?.auth.signOut();
    setRepId(null);
    router.replace("/login");
  }

  return (
    <RepContext.Provider value={{ selectedRep, isAuthLoading, signOut }}>{children}</RepContext.Provider>
  );
}

export function useRep(): RepContextValue {
  const context = useContext(RepContext);
  if (!context) {
    throw new Error("useRep は RepProvider の内側で使ってください");
  }
  return context;
}

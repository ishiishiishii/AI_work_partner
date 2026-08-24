"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { fetchReps } from "@/lib/api";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import type { SalesRep } from "@/types";

type RepContextValue = {
  reps: SalesRep[];
  selectedRep: SalesRep | null;
  setSelectedRepId: (repId: number) => void;
  isAuthLoading: boolean;
  signOut: () => Promise<void>;
};

const RepContext = createContext<RepContextValue | null>(null);

// ログインしていなくても見られる画面
const PUBLIC_PATHS = ["/login"];

export function RepProvider({ children }: { children: React.ReactNode }) {
  // authenticatedRepId: ログインしているかどうかの判定に使う(アクセス制御)
  // selectedRepId: 画面に表示する担当者。ログイン後は自由に切り替えられる
  const [authenticatedRepId, setAuthenticatedRepId] = useState<number | null>(null);
  const [selectedRepId, setSelectedRepId] = useState<number | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [reps, setReps] = useState<SalesRep[]>([]);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    fetchReps()
      .then(setReps)
      .catch((error) => {
        console.error("担当者一覧の取得に失敗しました", error);
      });
  }, []);

  useEffect(() => {
    const supabase = getSupabaseBrowserClient();
    if (!supabase) {
      setIsAuthLoading(false);
      return;
    }

    function applySession(repId: number | null) {
      setAuthenticatedRepId(repId);
      setSelectedRepId(repId);
    }

    supabase.auth.getSession().then(({ data }) => {
      applySession((data.session?.user.app_metadata.rep_id as number | undefined) ?? null);
      setIsAuthLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      applySession((session?.user.app_metadata.rep_id as number | undefined) ?? null);
    });

    return () => listener.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (isAuthLoading) return;
    const isPublicPath = PUBLIC_PATHS.includes(pathname);
    if (authenticatedRepId === null && !isPublicPath) {
      router.replace("/login");
    }
  }, [isAuthLoading, authenticatedRepId, pathname, router]);

  const selectedRep =
    selectedRepId !== null ? (reps.find((rep) => rep.rep_id === selectedRepId) ?? null) : null;

  async function signOut() {
    const supabase = getSupabaseBrowserClient();
    await supabase?.auth.signOut();
    setAuthenticatedRepId(null);
    setSelectedRepId(null);
    router.replace("/login");
  }

  return (
    <RepContext.Provider
      value={{ reps, selectedRep, setSelectedRepId, isAuthLoading, signOut }}
    >
      {children}
    </RepContext.Provider>
  );
}

export function useRep(): RepContextValue {
  const context = useContext(RepContext);
  if (!context) {
    throw new Error("useRep は RepProvider の内側で使ってください");
  }
  return context;
}

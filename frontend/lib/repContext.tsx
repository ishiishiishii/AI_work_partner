"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { fetchReps } from "@/lib/api";
import {
  getAuthenticatedRepId,
  signInSalesRep,
  signOutSalesRep,
} from "@/lib/supabase";
import type { SalesRep } from "@/types";

type RepContextValue = {
  reps: SalesRep[];
  selectedRep: SalesRep | null;
  setSelectedRepId: (repId: number) => void;
  isAuthLoading: boolean;
  signIn: (repId: number, password: string) => Promise<boolean>;
  signOut: () => Promise<void>;
};

const RepContext = createContext<RepContextValue | null>(null);
const PUBLIC_PATHS = ["/login"];

export function RepProvider({ children }: { children: React.ReactNode }) {
  const [authenticatedRepId, setAuthenticatedRepId] = useState<number | null>(null);
  const [isSessionLoading, setIsSessionLoading] = useState(true);
  const [isRepListLoading, setIsRepListLoading] = useState(true);
  const [allReps, setAllReps] = useState<SalesRep[]>([]);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    fetchReps()
      .then(setAllReps)
      .catch((error) => console.error("担当者一覧の取得に失敗しました", error))
      .finally(() => setIsRepListLoading(false));
  }, []);

  useEffect(() => {
    getAuthenticatedRepId()
      .then(setAuthenticatedRepId)
      .finally(() => setIsSessionLoading(false));
  }, []);

  const isAuthLoading = isSessionLoading || isRepListLoading;

  useEffect(() => {
    if (isAuthLoading) return;
    if (authenticatedRepId === null && !PUBLIC_PATHS.includes(pathname)) {
      router.replace("/login");
    }
  }, [isAuthLoading, authenticatedRepId, pathname, router]);

  const selectedRep =
    authenticatedRepId === null
      ? null
      : allReps.find((rep) => rep.rep_id === authenticatedRepId) ?? null;
  const reps = selectedRep ? [selectedRep] : [];

  async function signIn(repId: number, password: string): Promise<boolean> {
    const authenticated = await signInSalesRep(repId, password);
    if (authenticated) setAuthenticatedRepId(repId);
    return authenticated;
  }

  async function signOut(): Promise<void> {
    await signOutSalesRep();
    setAuthenticatedRepId(null);
    router.replace("/login");
  }

  function setSelectedRepId(repId: number): void {
    if (repId !== authenticatedRepId) {
      console.warn("認証済み本人以外の担当者データへは切り替えられません");
    }
  }

  return (
    <RepContext.Provider
      value={{ reps, selectedRep, setSelectedRepId, isAuthLoading, signIn, signOut }}
    >
      {children}
    </RepContext.Provider>
  );
}

export function useRep(): RepContextValue {
  const context = useContext(RepContext);
  if (!context) throw new Error("useRep は RepProvider の内側で使ってください");
  return context;
}

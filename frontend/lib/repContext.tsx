"use client";

import { createContext, useContext, useState } from "react";
import { mockSalesReps } from "@/lib/mockData";
import type { SalesRep } from "@/types";

type RepContextValue = {
  reps: SalesRep[];
  selectedRep: SalesRep;
  setSelectedRepId: (repId: number) => void;
};

const RepContext = createContext<RepContextValue | null>(null);

export function RepProvider({ children }: { children: React.ReactNode }) {
  const [selectedRepId, setSelectedRepId] = useState(mockSalesReps[0].rep_id);
  const selectedRep = mockSalesReps.find((rep) => rep.rep_id === selectedRepId) ?? mockSalesReps[0];

  return (
    <RepContext.Provider value={{ reps: mockSalesReps, selectedRep, setSelectedRepId }}>
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

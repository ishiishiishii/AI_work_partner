"use client";

import { useRep } from "@/lib/repContext";

export function RepSwitcher() {
  const { selectedRep } = useRep();

  if (!selectedRep) {
    return null;
  }

  return (
    <div className="rep-switcher">
      <span className="rep-switcher__name">{selectedRep.rep_name}</span>
    </div>
  );
}

"use client";

import { useRep } from "@/lib/repContext";

export function RepSwitcher() {
  const { selectedRep, signOut } = useRep();

  if (!selectedRep) {
    return null;
  }

  return (
    <div className="rep-switcher">
      <span className="rep-switcher__name">{selectedRep.rep_name}さん</span>
      <button type="button" className="rep-switcher__signout" onClick={() => void signOut()}>
        ログアウト
      </button>
    </div>
  );
}

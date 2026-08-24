"use client";

import { useRep } from "@/lib/repContext";

export function RepSwitcher() {
  const { reps, selectedRep, setSelectedRepId, signOut } = useRep();

  if (!selectedRep) {
    return null;
  }

  return (
    <div className="rep-switcher">
      <select
        className="rep-switcher__select"
        value={selectedRep.rep_id}
        onChange={(event) => setSelectedRepId(Number(event.target.value))}
        aria-label="表示する担当者を切り替える"
      >
        {reps.map((rep) => (
          <option key={rep.rep_id} value={rep.rep_id}>
            {rep.rep_name}
          </option>
        ))}
      </select>
      <button type="button" className="rep-switcher__signout" onClick={() => void signOut()}>
        ログアウト
      </button>
    </div>
  );
}

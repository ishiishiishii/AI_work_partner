"use client";

import { useRep } from "@/lib/repContext";

export function RepSwitcher() {
  const { reps, selectedRep, setSelectedRepId } = useRep();

  return (
    <select
      className="rep-switcher"
      value={selectedRep.rep_id}
      onChange={(event) => setSelectedRepId(Number(event.target.value))}
      aria-label="担当者を切り替える"
    >
      {reps.map((rep) => (
        <option key={rep.rep_id} value={rep.rep_id}>
          {rep.rep_name}
        </option>
      ))}
    </select>
  );
}

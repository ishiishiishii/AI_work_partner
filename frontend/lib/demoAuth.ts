const FIRST_DEMO_REP_ID = 1;
const LAST_DEMO_REP_ID = 50;

export function employeeIdToRepId(employeeId: string): number | null {
  const match = /^EMP(\d{3})$/i.exec(employeeId.trim());
  if (!match) return null;

  const repId = Number(match[1]);
  if (repId < FIRST_DEMO_REP_ID || repId > LAST_DEMO_REP_ID) return null;
  return repId;
}

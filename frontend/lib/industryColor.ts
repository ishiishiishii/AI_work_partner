// 業界名から決定的にHSL色相を割り当てる。業界マスタが増えても追従できるよう、
// ハードコードの対応表ではなくハッシュベースにしている(同じ業界名なら常に同じ色相)。
const HUE_STEP = 47; // 360の約数ではない値にして、少ない業種数でも色相が固まりにくくする

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i++) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return hash;
}

export function industryHue(industryName: string): number {
  return (hashString(industryName) * HUE_STEP) % 360;
}

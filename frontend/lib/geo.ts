// customer.location はデモ用の架空住所("茨城県水戸市宮町5-23-7"のような形式)で、
// 都道府県・市区町村は実在するが番地は架空(feature/customer-address-detail参照)。
// 番地が実在しない以上、外部ジオコーディングAPIで正確な座標を得る意味は薄いため、
// 都道府県庁所在地の座標(既知の実データ、47件固定)に、顧客ごとの決定的な小さいズレを
// 足すだけで地図上に散らす。外部API呼び出しが一切無いので、ネットワーク障害やAPIキー
// 管理の心配がない。

// [lat, lng] 、都道府県庁所在地
const PREFECTURE_COORDS: Record<string, [number, number]> = {
  北海道: [43.0642, 141.3469],
  青森県: [40.8244, 140.74],
  岩手県: [39.7036, 141.1527],
  宮城県: [38.2682, 140.8694],
  秋田県: [39.7186, 140.1024],
  山形県: [38.2404, 140.3633],
  福島県: [37.7503, 140.4676],
  茨城県: [36.3418, 140.4468],
  栃木県: [36.5658, 139.8836],
  群馬県: [36.3907, 139.0604],
  埼玉県: [35.8569, 139.6489],
  千葉県: [35.6047, 140.1233],
  東京都: [35.6895, 139.6917],
  神奈川県: [35.4478, 139.6425],
  新潟県: [37.9026, 139.0232],
  富山県: [36.6953, 137.2113],
  石川県: [36.5947, 136.6256],
  福井県: [36.0652, 136.2216],
  山梨県: [35.6642, 138.5684],
  長野県: [36.6513, 138.181],
  岐阜県: [35.3912, 136.7223],
  静岡県: [34.9769, 138.3831],
  愛知県: [35.1802, 136.9066],
  三重県: [34.7303, 136.5086],
  滋賀県: [35.0045, 135.8686],
  京都府: [35.0212, 135.7556],
  大阪府: [34.6937, 135.5023],
  兵庫県: [34.6913, 135.183],
  奈良県: [34.6851, 135.8048],
  和歌山県: [34.2261, 135.1675],
  鳥取県: [35.5039, 134.2381],
  島根県: [35.4723, 133.0505],
  岡山県: [34.6551, 133.9195],
  広島県: [34.3966, 132.4596],
  山口県: [34.1859, 131.4714],
  徳島県: [34.0658, 134.5593],
  香川県: [34.3401, 134.0434],
  愛媛県: [33.8416, 132.766],
  高知県: [33.5597, 133.5311],
  福岡県: [33.6064, 130.4181],
  佐賀県: [33.2494, 130.2988],
  長崎県: [32.7448, 129.8737],
  熊本県: [32.7898, 130.7417],
  大分県: [33.2382, 131.6126],
  宮崎県: [31.9111, 131.4239],
  鹿児島県: [31.5602, 130.5581],
  沖縄県: [26.2124, 127.6809],
};

// customer_id など整数を種にした決定的な擬似乱数(0以上1未満)。Math.random だと
// 再読み込みのたびにピンの位置が変わってしまうため、常に同じ値を返す必要がある。
function seededRandom(seed: number): number {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

export type CustomerPin = {
  customerId: number;
  customerName: string;
  location: string;
  lat: number;
  lng: number;
};

// location文字列の先頭に一致する都道府県名を返す(担当エリアでの絞り込みに使う)。
export function locationPrefecture(location: string): string | null {
  return Object.keys(PREFECTURE_COORDS).find((name) => location.startsWith(name)) ?? null;
}

// location文字列の先頭の都道府県名を拾い、その庁所在地の座標に、customer_id由来の
// 決定的なズレ(最大で緯度経度それぞれ約±0.3度 = 都道府県内に収まる程度)を加える。
// 該当する都道府県が見つからない場合は東京を仮の中心地とする。
export function estimateCoordinates(location: string, customerId: number): [number, number] {
  const prefecture = locationPrefecture(location);
  const [baseLat, baseLng] = PREFECTURE_COORDS[prefecture ?? "東京都"];
  const jitterLat = (seededRandom(customerId) - 0.5) * 0.6;
  const jitterLng = (seededRandom(customerId + 100000) - 0.5) * 0.6;
  return [baseLat + jitterLat, baseLng + jitterLng];
}

// 国土地理院APIで市区町村レベルの実座標が取れている顧客はそちらを優先し、
// まだジオコーディングが済んでいない(バックエンドがバックグラウンドで少しずつ埋めている
// 途中の)顧客だけ、従来の都道府県+ランダムズレにフォールバックする。
export function coordinatesForCustomer(customer: {
  location: string;
  customer_id: number;
  lat: number | null;
  lng: number | null;
}): [number, number] {
  if (customer.lat !== null && customer.lng !== null) {
    return [customer.lat, customer.lng];
  }
  return estimateCoordinates(customer.location, customer.customer_id);
}

// 担当エリア(都道府県名の配列)の庁所在地群を包む範囲を返す。ピンが1件も無い時
// (読み込み中・顧客0件)の地図の初期表示に使うフォールバック。
export function boundsForPrefectures(prefectures: string[]): [[number, number], [number, number]] {
  const coords = prefectures
    .map((name) => PREFECTURE_COORDS[name])
    .filter((coord): coord is [number, number] => coord !== undefined);
  const base: [number, number][] = coords.length > 0 ? coords : [PREFECTURE_COORDS["東京都"]];

  const margin = 0.2;
  const lats = base.map(([lat]) => lat);
  const lngs = base.map(([, lng]) => lng);
  return [
    [Math.min(...lats) - margin, Math.min(...lngs) - margin],
    [Math.max(...lats) + margin, Math.max(...lngs) + margin],
  ];
}

// 実際に表示するピンの座標そのものを包む範囲を返す。県庁所在地ベースの概算ではなく
// 実データに合わせるので、顧客が1都市に集中していれば自然にその街まで寄って表示され、
// 複数県に散らばっていれば自然にそれを収める倍率になる(地図側のpaddingピクセルで
// 見た目の余白を調整する。lib/components/dashboard/MapPanel.tsx参照)。
export function boundsForPositions(positions: [number, number][]): [[number, number], [number, number]] {
  const lats = positions.map(([lat]) => lat);
  const lngs = positions.map(([, lng]) => lng);
  return [
    [Math.min(...lats), Math.min(...lngs)],
    [Math.max(...lats), Math.max(...lngs)],
  ];
}

"use client";

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import { boundsForPositions, boundsForPrefectures, coordinatesForCustomer, locationPrefecture } from "@/lib/geo";
import type { ActivityPlan, Customer, Territory } from "@/types";

// leafletのデフォルトマーカー画像はCSS相対パス経由で読み込まれる前提になっており、
// webpack/Next.jsのバンドル環境ではパスが壊れて透明な四角になる定番の問題がある。
// アイコン画像を明示的にimportしてバンドラ管理下に置き、パスを組み直す。
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

delete (L.Icon.Default.prototype as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x.src,
  iconUrl: markerIcon.src,
  shadowUrl: markerShadow.src,
});

type MapPanelProps = {
  customers: Customer[];
  territory: Territory | null;
  plans: ActivityPlan[];
  targetMonth: string; // "YYYY-MM"
};

const JAPAN_BOUNDS: [[number, number], [number, number]] = [
  [26, 128],
  [45.5, 145.8],
];

// ピンを囲む余白(ピクセル指定なので、都市1つ分でも県またぎでも見た目の余白が揃う)。
// maxZoomは、ピンが1件しかない・1箇所に密集している時に寄りすぎて建物レベルまで
// 拡大されるのを防ぐための上限。
const FIT_BOUNDS_OPTIONS = { padding: [32, 32] as [number, number], maxZoom: 11 };

export function MapPanel({ customers, territory, plans, targetMonth }: MapPanelProps) {
  // 担当エリア(担当営業所が管轄する都道府県)の企業のみに絞り込む。territory未取得中
  // (読み込み中)は絞り込まず全件表示しておく方が「一瞬空になる」より自然。
  const territoryCustomers = territory
    ? customers.filter((customer) => {
        const prefecture = locationPrefecture(customer.location);
        return prefecture !== null && territory.prefectures.includes(prefecture);
      })
    : customers;

  // ピンが多すぎて見づらいとの指摘を受け、今月の計画にある顧客だけに絞り込む。
  // 今月の計画がまだ無ければ、そのまま何も表示しない(フォールバックしない)。
  const plannedCustomerIds = new Set(
    plans
      .filter((plan) => plan.customer_id !== null && plan.plan_date.startsWith(targetMonth))
      .map((plan) => plan.customer_id as number),
  );
  const scopedCustomers = territoryCustomers.filter((customer) =>
    plannedCustomerIds.has(customer.customer_id),
  );

  const pins = scopedCustomers.map((customer) => ({
    customer,
    position: coordinatesForCustomer(customer),
  }));

  const bounds =
    pins.length > 0
      ? boundsForPositions(pins.map((pin) => pin.position))
      : territory
        ? boundsForPrefectures(territory.prefectures)
        : JAPAN_BOUNDS;

  return (
    <section className="panel map-panel">
      <h2>
        顧客の分布{territory && `(${territory.branch_name}エリア)`}・今月の計画分
      </h2>
      <div className="map-panel__leaflet">
        <MapContainer
          key={territory?.branch_name ?? "japan"}
          bounds={bounds}
          boundsOptions={FIT_BOUNDS_OPTIONS}
          scrollWheelZoom={false}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {pins.map(({ customer, position }) => (
            <Marker key={customer.customer_id} position={position}>
              <Popup>
                <strong>{customer.customer_name}</strong>
                <br />
                {customer.location}
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>
    </section>
  );
}

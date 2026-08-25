"use client";

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import { boundsForPrefectures, coordinatesForCustomer, locationPrefecture } from "@/lib/geo";
import type { Customer, Territory } from "@/types";

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
};

const JAPAN_BOUNDS: [[number, number], [number, number]] = [
  [26, 128],
  [45.5, 145.8],
];

export function MapPanel({ customers, territory }: MapPanelProps) {
  // 担当エリア(担当営業所が管轄する都道府県)の企業のみに絞り込む。territory未取得中
  // (読み込み中)は絞り込まず全件表示しておく方が「一瞬空になる」より自然。
  const scopedCustomers = territory
    ? customers.filter((customer) => {
        const prefecture = locationPrefecture(customer.location);
        return prefecture !== null && territory.prefectures.includes(prefecture);
      })
    : customers;

  const pins = scopedCustomers.map((customer) => ({
    customer,
    position: coordinatesForCustomer(customer),
    isGeocoded: customer.lat !== null && customer.lng !== null,
  }));
  const geocodedCount = pins.filter((pin) => pin.isGeocoded).length;

  const bounds = territory ? boundsForPrefectures(territory.prefectures) : JAPAN_BOUNDS;

  return (
    <section className="panel map-panel">
      <h2>顧客の分布{territory && `(${territory.branch_name}エリア)`}</h2>
      <p className="map-panel__note">
        番地はデモ用の架空データのため考慮していませんが、市区町村までは実在の位置です
        {pins.length > 0 && geocodedCount < pins.length && "(一部、位置情報の取得が完了するまでは都道府県内のおおよその位置で表示されます)"}
        。
      </p>
      <div className="map-panel__leaflet">
        <MapContainer bounds={bounds} scrollWheelZoom={false}>
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

"use client";

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import { estimateCoordinates } from "@/lib/geo";
import type { Customer } from "@/types";

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
};

const JAPAN_CENTER: [number, number] = [36.5, 138];

export function MapPanel({ customers }: MapPanelProps) {
  const pins = customers.map((customer) => ({
    customer,
    position: estimateCoordinates(customer.location, customer.customer_id),
  }));

  return (
    <section className="panel map-panel">
      <h2>顧客の分布</h2>
      <p className="map-panel__note">
        住所の番地はデモ用の架空データのため、ピンの位置は都道府県内のおおよその位置です。
      </p>
      <div className="map-panel__leaflet">
        <MapContainer center={JAPAN_CENTER} zoom={5} scrollWheelZoom={false}>
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

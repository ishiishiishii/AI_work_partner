// TODO: 商談先などの地図表示に差し替える。現在は仮画像
export function MapPanel() {
  return (
    <section className="panel map-panel">
      <h2>地図</h2>
      <div className="map-panel__placeholder">
        <img
          src="/images/ai-chat-map-placeholder.jpg"
          alt="地図表示エリア（準備中）"
          className="map-panel__placeholder-image"
        />
        <span className="map-panel__placeholder-label">準備中</span>
      </div>
    </section>
  );
}

type CategoryBarChartItem = {
  label: string;
  value: number; // 0-100
  count: number;
};

type CategoryBarChartProps = {
  title: string;
  items: CategoryBarChartItem[];
  color: string;
};

// 単一系列の横棒グラフ。件数0の項目も含めて全項目を軸に出すことで、
// 「まだ実績が無い分野」も含めた得意・不得意の全体像が分かるようにしている。
export function CategoryBarChart({ title, items, color }: CategoryBarChartProps) {
  const sorted = [...items].sort((a, b) => b.value - a.value);

  return (
    <div className="category-bar-chart">
      <h4 className="category-bar-chart__title">{title}</h4>
      <ul className="category-bar-chart__list">
        {sorted.map((item) => (
          <li key={item.label} className="category-bar-chart__row">
            <span className="category-bar-chart__label">{item.label}</span>
            <div className="category-bar-chart__track">
              <div
                className="category-bar-chart__fill"
                style={{ width: `${item.value}%`, background: color }}
              />
            </div>
            <span className="category-bar-chart__value">
              {item.count > 0 ? `${Math.round(item.value)}%` : "実績なし"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

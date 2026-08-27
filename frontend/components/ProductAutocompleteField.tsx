"use client";

import { useEffect, useState } from "react";
import { fetchProducts } from "@/lib/api";
import type { Product } from "@/types";

const SEARCH_DEBOUNCE_MS = 300;

type ProductAutocompleteFieldProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
};

// 商品名の入力補助。既存商品と一致する候補をプルダウン表示するが、新規商品の
// 追加はしない(商品マスタは営業担当からは編集不可)。候補にない名前でも
// これまで通り自由記述として保存できる。
export function ProductAutocompleteField({ value, onChange, placeholder }: ProductAutocompleteFieldProps) {
  const [suggestions, setSuggestions] = useState<Product[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  useEffect(() => {
    const query = value.trim();
    if (query.length < 1) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      fetchProducts(query)
        .then((results) => {
          if (cancelled) return;
          setSuggestions(results);
          setShowSuggestions(results.length > 0);
        })
        .catch(() => {
          if (!cancelled) setSuggestions([]);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [value]);

  return (
    <div className="new-customer-form__name-field">
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onFocus={() => setShowSuggestions(suggestions.length > 0)}
        onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
        placeholder={placeholder}
        autoComplete="off"
      />
      {showSuggestions && (
        <ul className="new-customer-form__suggestions">
          {suggestions.map((product) => (
            <li key={product.product_id}>
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  onChange(product.product_name);
                  setShowSuggestions(false);
                }}
              >
                <span className="new-customer-form__suggestion-name">{product.product_name}</span>
                <span className="new-customer-form__suggestion-meta">{product.category_name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

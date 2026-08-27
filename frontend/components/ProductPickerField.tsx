"use client";

import { useEffect, useState } from "react";
import { fetchProducts } from "@/lib/api";
import type { Product } from "@/types";

const SEARCH_DEBOUNCE_MS = 300;

export type ProductFieldValue = {
  productId: number | null;
  productName: string;
};

type ProductPickerFieldProps = {
  value: ProductFieldValue;
  onChange: (value: ProductFieldValue) => void;
  placeholder?: string;
};

// 商談の商品はマスタの商品(product_id)を指す必要があるため、予定の
// ProductAutocompleteFieldと違って自由記述は許可せず、検索して候補から
// 選ぶことを必須にする。
export function ProductPickerField({ value, onChange, placeholder }: ProductPickerFieldProps) {
  const [suggestions, setSuggestions] = useState<Product[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  useEffect(() => {
    const query = value.productName.trim();
    if (value.productId !== null || query.length < 1) {
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
  }, [value.productName, value.productId]);

  function handleNameChange(name: string) {
    onChange({ productId: null, productName: name });
  }

  function applySuggestion(product: Product) {
    onChange({ productId: product.product_id, productName: product.product_name });
    setShowSuggestions(false);
  }

  return (
    <div className="new-customer-form__name-field">
      <input
        type="text"
        value={value.productName}
        onChange={(event) => handleNameChange(event.target.value)}
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
                onClick={() => applySuggestion(product)}
              >
                <span className="new-customer-form__suggestion-name">{product.product_name}</span>
                <span className="new-customer-form__suggestion-meta">{product.category_name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {value.productId !== null && <span className="company-autocomplete__linked">選択済み</span>}
    </div>
  );
}

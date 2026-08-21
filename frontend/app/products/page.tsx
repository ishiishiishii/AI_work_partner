"use client";

import { useEffect, useState } from "react";
import { ProductCatalog } from "@/components/products/ProductCatalog";
import { fetchProducts } from "@/lib/api";
import type { Product } from "@/types";

export default function ProductsPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setIsLoading(true);
        setLoadError(null);
        const fetched = await fetchProducts(searchTerm || undefined);
        if (!cancelled) setProducts(fetched);
      } catch (error) {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : "読み込みに失敗しました");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [searchTerm]);

  function handleSearchSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSearchTerm(searchInput.trim());
  }

  return (
    <main>
      <h1>商品カタログ</h1>
      <p>取り扱っている商品をカテゴリ・サブカテゴリ別に確認できます。</p>

      <form className="product-search" onSubmit={handleSearchSubmit}>
        <input
          type="text"
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
          placeholder="商品名で検索(例: カメラ)"
        />
        <button type="submit" className="regenerate-button">
          検索
        </button>
        {searchTerm && (
          <button
            type="button"
            className="regenerate-button"
            onClick={() => {
              setSearchInput("");
              setSearchTerm("");
            }}
          >
            クリア
          </button>
        )}
      </form>

      {isLoading ? (
        <p>読み込み中...</p>
      ) : loadError ? (
        <p className="activity-plan-list__empty">
          データの取得に失敗しました({loadError})。バックエンド(API・Supabase)が起動しているか確認してください。
        </p>
      ) : (
        <ProductCatalog products={products} />
      )}
    </main>
  );
}

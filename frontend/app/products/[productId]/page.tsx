"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchProducts } from "@/lib/api";
import { getProductDummyDetails } from "@/lib/mockData";
import type { Product } from "@/types";

export default function ProductDetailPage() {
  const { productId } = useParams<{ productId: string }>();
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [product, setProduct] = useState<Product | null>(null);

  useEffect(() => {
    let cancelled = false;
    const targetId = Number(productId);

    async function load() {
      try {
        setIsLoading(true);
        setLoadError(null);
        const products = await fetchProducts();
        if (cancelled) return;
        setProduct(products.find((item) => item.product_id === targetId) ?? null);
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
  }, [productId]);

  if (isLoading) {
    return (
      <main>
        <p>読み込み中...</p>
      </main>
    );
  }

  if (loadError || !product) {
    return (
      <main>
        <p className="activity-plan-list__empty">
          {loadError ? `データの取得に失敗しました(${loadError})` : "この商品は見つかりませんでした"}
        </p>
        <Link href="/products">← 商品カタログに戻る</Link>
      </main>
    );
  }

  const details = getProductDummyDetails(product);

  return (
    <main>
      <Link href="/products" className="customer-detail__back">
        ← 商品カタログに戻る
      </Link>
      <h1>{product.product_name}</h1>
      <p>
        {product.category_name}・{product.subcategory_name}
      </p>

      <section className="panel">
        <p>{details.description}</p>
        <dl className="goal-card__numbers customer-detail__summary">
          <div>
            <dt>価格帯</dt>
            <dd>{details.priceRangeText}</dd>
          </div>
          <div>
            <dt>納期目安</dt>
            <dd>{details.leadTimeText}</dd>
          </div>
          <div>
            <dt>特徴</dt>
            <dd>{details.features.join("・")}</dd>
          </div>
        </dl>
        <p className="activity-plan-list__empty">
          ※ 商品の詳細スペックを管理するAPIがまだ無いため、上記は参考情報(ダミー)です。
        </p>
      </section>
    </main>
  );
}

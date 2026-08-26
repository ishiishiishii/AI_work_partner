"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchProducts } from "@/lib/api";
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

  const priceRangeText = `¥${product.price_min.toLocaleString("ja-JP")} 〜 ¥${product.price_max.toLocaleString("ja-JP")}`;
  const leadTimeText = `約${product.lead_time_days}営業日`;
  const monogram = product.product_name.charAt(0);

  return (
    <main className="wide-main product-detail">
      <Link href="/products" className="customer-detail__back">
        ← 商品カタログに戻る
      </Link>

      <section className="panel product-detail__hero">
        <div className="product-detail__monogram" aria-hidden="true">
          <span>{monogram}</span>
        </div>
        <div className="product-detail__hero-body">
          <div className="product-detail__breadcrumb">
            <span className="product-detail__tag">{product.category_name}</span>
            <span className="product-detail__breadcrumb-sep">/</span>
            <span className="product-detail__tag product-detail__tag--sub">{product.subcategory_name}</span>
          </div>
          <h1>{product.product_name}</h1>
          <div className="product-detail__quickfacts">
            <span className="product-detail__pill">
              <span className="product-detail__pill-label">価格帯</span>
              {priceRangeText}
            </span>
            <span className="product-detail__pill">
              <span className="product-detail__pill-label">納期</span>
              {leadTimeText}
            </span>
          </div>
        </div>
      </section>

      <div className="product-detail__layout">
        <section className="panel product-detail__stats-panel">
          <h2>スペック</h2>
          <dl className="product-detail__stats">
            <div className="product-detail__stat">
              <dt>価格帯</dt>
              <dd>{priceRangeText}</dd>
            </div>
            <div className="product-detail__stat">
              <dt>納期目安</dt>
              <dd>{leadTimeText}</dd>
            </div>
            <div className="product-detail__stat">
              <dt>カテゴリ</dt>
              <dd>{product.category_name}</dd>
            </div>
          </dl>
          <div className="product-detail__features">
            {product.features.map((feature) => (
              <span key={feature} className="product-detail__feature-chip">
                {feature}
              </span>
            ))}
          </div>
        </section>

        <section className="panel product-detail__description">
          <h2>商品概要</h2>
          <p>{product.description}</p>
        </section>
      </div>
    </main>
  );
}

import type { Product } from "@/types";

type ProductCatalogProps = {
  products: Product[];
};

type CategoryGroup = {
  category_id: number;
  category_name: string;
  subcategories: Map<number, { subcategory_name: string; products: Product[] }>;
};

function groupByCategory(products: Product[]): CategoryGroup[] {
  const categories = new Map<number, CategoryGroup>();

  for (const product of products) {
    let category = categories.get(product.category_id);
    if (!category) {
      category = {
        category_id: product.category_id,
        category_name: product.category_name,
        subcategories: new Map(),
      };
      categories.set(product.category_id, category);
    }

    let subcategory = category.subcategories.get(product.subcategory_id);
    if (!subcategory) {
      subcategory = { subcategory_name: product.subcategory_name, products: [] };
      category.subcategories.set(product.subcategory_id, subcategory);
    }
    subcategory.products.push(product);
  }

  return [...categories.values()].sort((a, b) => a.category_name.localeCompare(b.category_name, "ja"));
}

export function ProductCatalog({ products }: ProductCatalogProps) {
  if (products.length === 0) {
    return <p className="activity-plan-list__empty">該当する商品がありません</p>;
  }

  const groups = groupByCategory(products);

  return (
    <div className="product-catalog">
      {groups.map((category) => (
        <section key={category.category_id} className="panel product-catalog__category">
          <h2>{category.category_name}</h2>
          {[...category.subcategories.entries()]
            .sort(([, a], [, b]) => a.subcategory_name.localeCompare(b.subcategory_name, "ja"))
            .map(([subcategoryId, subcategory]) => (
              <div key={subcategoryId} className="product-catalog__subcategory">
                <h3>{subcategory.subcategory_name}</h3>
                <ul className="product-catalog__list">
                  {subcategory.products
                    .sort((a, b) => a.product_name.localeCompare(b.product_name, "ja"))
                    .map((product) => (
                      <li key={product.product_id} className="product-catalog__item">
                        {product.product_name}
                      </li>
                    ))}
                </ul>
              </div>
            ))}
        </section>
      ))}
    </div>
  );
}

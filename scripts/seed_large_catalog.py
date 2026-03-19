#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import Category, Product, ProductMedia, ProductSku


DEFAULT_BASE_URL = (
    "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/"
    "product-images/product-images/categories"
)
DEFAULT_LOCAL_ASSET_ROOT = "/Users/chandyoung/Pictures/tea-assets-webp/categories"


@dataclass(frozen=True)
class CategorySpec:
    id: str
    name: str
    sort: int


CATEGORY_SPECS: dict[str, CategorySpec] = {
    "tea_bag": CategorySpec("cat_tea_bag", "袋茶", 1),
    "tea_pack": CategorySpec("cat_tea_pack", "包茶", 2),
    "teaware": CategorySpec("cat_teaware", "茶具", 3),
    "tea_product": CategorySpec("cat_tea_product", "茶制品", 4),
    "green_tea": CategorySpec("cat_green_tea", "绿茶", 5),
    "black_tea": CategorySpec("cat_black_tea", "红茶", 6),
    "flower_tea": CategorySpec("cat_flower_tea", "花茶", 7),
    "white_tea": CategorySpec("cat_white_tea", "白茶", 8),
}


NAME_POOLS: dict[str, list[str]] = {
    "tea_bag": ["袋泡清香绿茶", "袋泡红茶", "袋泡花果茶", "袋泡乌龙茶", "袋泡白茶"],
    "tea_pack": ["高山绿茶", "碧螺春", "银针绿茶", "白毛豪尖", "花香乌龙", "陈香普洱"],
    "teaware": ["玻璃公道杯", "紫砂茶壶", "白瓷盖碗", "茶滤套装", "闻香杯套组"],
    "tea_product": ["茶点礼盒", "抹茶粉", "茶香糕点", "冻干茶块", "茶酥小食"],
    "green_tea": ["明前绿茶", "龙井绿茶", "炒青绿茶", "高山云雾绿茶", "茉香绿茶"],
    "black_tea": ["祁门红茶", "滇红工夫", "正山小种", "金骏眉", "迎香红茶"],
    "flower_tea": ["玫瑰花茶", "茉莉花茶", "桂花乌龙", "菊花花茶", "洛神花茶"],
    "white_tea": ["白毫银针", "白牡丹", "贡眉白茶", "寿眉白茶", "福鼎白茶"],
}

BADGE_PRIMARY = ["新品", "热销", "推荐", "口碑", "回购高"]
BADGE_SECONDARY = ["限时折扣", "月销优选", "春茶上新", "店长推荐", "高分好评"]
SPEC_NAMES = ["体验装", "标准装", "礼盒装"]


def iter_local_assets(local_asset_root: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for slug in CATEGORY_SPECS:
        cat_dir = local_asset_root / slug
        if not cat_dir.exists():
            continue
        files = sorted([p.name for p in cat_dir.iterdir() if p.is_file() and p.suffix.lower() == ".webp"])
        if files:
            result[slug] = files
    return result


def ensure_categories(db, used_slugs: list[str]) -> dict[str, Category]:
    category_by_slug: dict[str, Category] = {}
    for slug in used_slugs:
        spec = CATEGORY_SPECS[slug]
        category = db.get(Category, spec.id)
        if not category:
            # Reuse existing category by name to avoid unique(name) conflicts.
            category = db.execute(select(Category).where(Category.name == spec.name)).scalars().first()
            if not category:
                category = Category(id=spec.id, name=spec.name, sort_order=spec.sort)
                db.add(category)
            else:
                category.sort_order = spec.sort
        else:
            category.name = spec.name
            category.sort_order = spec.sort
        category_by_slug[slug] = category
    db.flush()
    return category_by_slug


def create_or_update_product(
    *,
    db,
    product_id: str,
    name: str,
    subtitle: str,
    category_id: str,
    market_price_cent: int,
    sold_count: int,
    badge_primary: str,
    badge_secondary: str,
    image_urls: list[str],
    rng: random.Random,
):
    product = db.get(Product, product_id)
    if not product:
        product = Product(id=product_id, name=name, category_id=category_id)
        db.add(product)

    product.name = name
    product.subtitle = subtitle
    product.category_id = category_id
    product.description = f"{name}，茶香清雅，适合日常冲泡。"
    product.market_price_cent = market_price_cent
    product.sold_count = sold_count
    product.badge_primary = badge_primary
    product.badge_secondary = badge_secondary
    product.status = "active"

    db.execute(delete(ProductSku).where(ProductSku.product_id == product_id))
    db.execute(delete(ProductMedia).where(ProductMedia.product_id == product_id))

    base_price = max(2900, int(market_price_cent * 0.72))
    for idx, spec_name in enumerate(SPEC_NAMES, start=1):
        price = max(900, base_price + (idx - 2) * 1500)
        stock = rng.randint(30, 220)
        db.add(
            ProductSku(
                id=f"{product_id}_sku_{idx}",
                product_id=product_id,
                sku_name=spec_name,
                price_cent=price,
                stock=stock,
            )
        )

    for idx, url in enumerate(image_urls, start=1):
        db.add(
            ProductMedia(
                id=f"{product_id}_media_{idx}",
                product_id=product_id,
                media_url=url,
                sort_order=idx,
            )
        )


def seed_large_catalog(
    *,
    base_url: str,
    local_asset_root: Path,
    variants_per_image: int,
    seed: int,
) -> tuple[int, int]:
    assets = iter_local_assets(local_asset_root)
    if not assets:
        raise RuntimeError(f"No .webp assets found under: {local_asset_root}")

    rng = random.Random(seed)
    used_slugs = sorted(assets.keys())
    created_products = 0

    with SessionLocal() as db:
        category_by_slug = ensure_categories(db, used_slugs)

        for slug in used_slugs:
            files = assets[slug]
            pool = NAME_POOLS[slug]
            category_id = category_by_slug[slug].id
            for img_idx, filename in enumerate(files, start=1):
                cover = f"{base_url}/{slug}/{filename}"
                alt1 = f"{base_url}/{slug}/{files[(img_idx) % len(files)]}"
                alt2 = f"{base_url}/{slug}/{files[(img_idx + 1) % len(files)]}"
                for variant in range(1, variants_per_image + 1):
                    name = f"{pool[(img_idx + variant - 2) % len(pool)]}·{variant}号"
                    product_id = f"bulk_{slug}_{img_idx:02d}_{variant:02d}"
                    subtitle = f"{CATEGORY_SPECS[slug].name}精选款，口感稳定，日常推荐"
                    market_price = rng.randint(5900, 25900)
                    sold_count = rng.randint(10, 1800)
                    badge_primary = BADGE_PRIMARY[(img_idx + variant - 2) % len(BADGE_PRIMARY)]
                    badge_secondary = BADGE_SECONDARY[(img_idx + variant - 2) % len(BADGE_SECONDARY)]
                    create_or_update_product(
                        db=db,
                        product_id=product_id,
                        name=name,
                        subtitle=subtitle,
                        category_id=category_id,
                        market_price_cent=market_price,
                        sold_count=sold_count,
                        badge_primary=badge_primary,
                        badge_secondary=badge_secondary,
                        image_urls=[cover, alt1, alt2],
                        rng=rng,
                    )
                    created_products += 1

        db.commit()

        active_count = (
            db.execute(select(Product).where(Product.status == "active"))
            .scalars()
            .all()
        )
        return created_products, len(active_count)


def main():
    parser = argparse.ArgumentParser(description="Seed many active products using category image assets.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Public base URL of categories images.")
    parser.add_argument("--local-asset-root", default=DEFAULT_LOCAL_ASSET_ROOT, help="Local webp categories folder.")
    parser.add_argument(
        "--variants-per-image",
        type=int,
        default=3,
        help="How many products to create per image.",
    )
    parser.add_argument("--seed", type=int, default=20260310, help="Random seed for deterministic data.")
    args = parser.parse_args()

    if args.variants_per_image < 1:
        raise SystemExit("variants-per-image must be >= 1")

    created, total_active = seed_large_catalog(
        base_url=args.base_url.rstrip("/"),
        local_asset_root=Path(args.local_asset_root),
        variants_per_image=args.variants_per_image,
        seed=args.seed,
    )
    print(f"Seed completed: created_or_updated={created}, total_active_products={total_active}")


if __name__ == "__main__":
    main()

"""Phase 2 数据迁移 — 为已有表添加新字段

执行方式:
    python migrate_phase2.py

迁移内容:
1. products 表添加 weather_sensitive (BOOLEAN DEFAULT FALSE)
2. products 表添加 weather_type (JSON NULL)
3. product_categories 表添加 bullwhip_threshold (FLOAT DEFAULT 1.5)
4. 创建新表 supplier_metrics (由 create_all 自动完成)
"""

from sqlalchemy import text, inspect
from app.database import engine, Base, SessionLocal

# 导入所有模型以确保 create_all 能识别
from app.models import *  # noqa


def column_exists(table_name: str, column_name: str) -> bool:
    insp = inspect(engine)
    columns = [col["name"] for col in insp.get_columns(table_name)]
    return column_name in columns


def table_exists(table_name: str) -> bool:
    insp = inspect(engine)
    return table_name in insp.get_table_names()


def migrate():
    # 1. 先 create_all 确保新表 supplier_metrics 被创建
    Base.metadata.create_all(bind=engine)
    print("✓ create_all 完成（新表自动创建）")

    with engine.begin() as conn:
        # 2. products 添加字段
        if not column_exists("products", "weather_sensitive"):
            conn.execute(text(
                "ALTER TABLE products ADD COLUMN weather_sensitive BOOLEAN DEFAULT FALSE"
            ))
            print("✓ products.weather_sensitive 添加完成")
        else:
            print("· products.weather_sensitive 已存在，跳过")

        if not column_exists("products", "weather_type"):
            conn.execute(text(
                "ALTER TABLE products ADD COLUMN weather_type JSON NULL"
            ))
            print("✓ products.weather_type 添加完成")
        else:
            print("· products.weather_type 已存在，跳过")

        # 3. product_categories 添加字段
        if not column_exists("product_categories", "bullwhip_threshold"):
            conn.execute(text(
                "ALTER TABLE product_categories ADD COLUMN bullwhip_threshold FLOAT DEFAULT 1.5"
            ))
            print("✓ product_categories.bullwhip_threshold 添加完成")
        else:
            print("· product_categories.bullwhip_threshold 已存在，跳过")

    # 4. 验证
    print("\n验证结果:")
    insp = inspect(engine)
    for table_name in ["products", "product_categories", "supplier_metrics"]:
        cols = [col["name"] for col in insp.get_columns(table_name)]
        print(f"  {table_name}: {cols}")

    print("\n✅ Phase 2 迁移完成！")


if __name__ == "__main__":
    migrate()

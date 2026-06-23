"""FastAPI 主入口"""
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.config import settings
from app.database import Base, engine
from app.routers import auth, supplier, product, purchase, inventory, sale, ai_decision, ai_chat

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

logger = logging.getLogger(__name__)
logger.info("日志系统已就绪")


def _auto_add_columns():
    """检测模型定义的列 vs 数据库实际列，自动 ALTER TABLE 补缺列"""
    from sqlalchemy import String, Text, JSON, LargeBinary
    _NO_DEFAULT_TYPES = (String, Text, JSON, LargeBinary)

    insp = inspect(engine)
    for table_name, orm_table in Base.metadata.tables.items():
        if not insp.has_table(table_name):
            continue
        db_cols = {col["name"] for col in insp.get_columns(table_name)}
        model_cols = {col.name for col in orm_table.columns}
        missing = model_cols - db_cols
        for col_name in missing:
            col_obj = orm_table.columns[col_name]
            col_type = col_obj.type.compile(dialect=engine.dialect)
            parts = [f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"]

            is_no_default_type = isinstance(col_obj.type, _NO_DEFAULT_TYPES)
            has_default = False

            if is_no_default_type:
                # MySQL 不允许 TEXT/BLOB/JSON 列有 DEFAULT 值
                pass
            elif col_obj.server_default is not None:
                sd_text = getattr(col_obj.server_default, "arg", col_obj.server_default)
                if hasattr(sd_text, "text"):
                    sd_text = sd_text.text
                if isinstance(sd_text, str) and sd_text:
                    parts.append(f"DEFAULT {sd_text}")
                    has_default = True
            elif col_obj.default is not None and not callable(col_obj.default.arg):
                val = col_obj.default.arg
                if isinstance(val, bool):
                    parts.append(f"DEFAULT {1 if val else 0}")
                elif isinstance(val, str):
                    parts.append(f"DEFAULT '{val}'")
                elif val is not None:
                    parts.append(f"DEFAULT {val}")
                has_default = True

            # NOT NULL 列必须有默认值，否则 ALTER 在有数据时会失败
            if not col_obj.nullable and has_default:
                parts.append("NOT NULL")
            elif not col_obj.nullable and not has_default:
                logger.warning(f"自动补列跳过 NOT NULL: {col_name} (无默认值，先允许 NULL)")

            sql = " ".join(parts)
            logger.info(f"自动补列: {sql}")
            with engine.begin() as conn:
                conn.execute(text(sql))


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _auto_add_columns()
    yield


app = FastAPI(
    title="供应链ERP系统",
    description="供应链进销存管理系统 + AI 智能决策",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = (time.time() - start) * 1000
    msg = f"{request.method} {request.url.path} → {response.status_code} ({elapsed:.0f}ms)"
    print(msg, flush=True)
    logger.info(msg)
    return response

# 注册路由
app.include_router(auth.router)
app.include_router(supplier.router)
app.include_router(product.router)
app.include_router(purchase.router)
app.include_router(inventory.router)
app.include_router(sale.router)
app.include_router(ai_decision.router)
app.include_router(ai_chat.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "供应链ERP系统"}

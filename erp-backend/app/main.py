"""FastAPI 主入口"""
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth, supplier, product, purchase, inventory, sale, ai_decision, ai_chat

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

logger = logging.getLogger(__name__)
logger.info("日志系统已就绪")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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

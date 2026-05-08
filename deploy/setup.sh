#!/bin/bash
set -euo pipefail

# ============================================================
# ERP 系统 — Docker 一键部署初始化脚本
# 服务器只需要安装 Docker + Docker Compose
# ============================================================

ERPDIR="/var/www/erp-system"
LOG_FILE="$ERPDIR/logs/setup.log"

mkdir -p "$ERPDIR/logs"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "===== ERP 系统初始化开始: $(date) ====="

# ── 1. 安装 Docker（国内镜像）────────────────────────
echo "[1/4] 安装 Docker..."
if ! command -v docker &>/dev/null; then
    # 使用腾讯云镜像安装 Docker
    curl -fsSL https://mirrors.cloud.tencent.com/docker-ce/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.cloud.tencent.com/docker-ce/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    echo "Docker 安装完成 ✓"
else
    echo "Docker 已安装"
fi

# ── 2. 配置 Docker 镜像加速 ──────────────────────────
echo "[2/4] 配置 Docker 镜像加速..."
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << EOF
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.m.daocloud.io"
  ]
}
EOF
systemctl restart docker
echo "镜像加速已配置 ✓"

# ── 3. 启动所有服务 ──────────────────────────────────
echo "[3/4] 构建并启动所有服务..."
cd "$ERPDIR"
docker compose build --parallel
docker compose up -d
echo "服务启动完成 ✓"

# ── 4. 初始化种子数据 ────────────────────────────────
echo "[4/4] 导入种子数据..."
# 等待后端就绪
echo "等待后端服务就绪..."
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1/api/auth/me > /dev/null 2>&1; then
        echo "后端就绪 ✓"
        break
    fi
    sleep 2
done

# 在容器中运行种子数据脚本
docker compose exec -T backend python seed_data.py 2>/dev/null || echo "种子数据可能已存在"
echo "种子数据初始化完成 ✓"

echo ""
echo "===== 初始化完成 ====="
echo "访问地址: http://111.229.232.23"
echo "默认账号: admin / admin123"
echo "========================="

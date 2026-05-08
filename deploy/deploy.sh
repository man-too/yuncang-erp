#!/bin/bash
set -euo pipefail

# ============================================================
# ERP 系统 — 远程部署脚本
# 由 GitHub Actions 通过 SSH 调用
# 参数: $1 — .env 文件内容（从 GitHub Secret 传入）
# ============================================================

ERPDIR="/var/www/erp-system"
LOG_FILE="$ERPDIR/logs/deploy-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "$ERPDIR/logs"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "===== 部署开始: $(date) ====="

# ── 1. 写入 .env（从 GitHub Secret 传入）─────────────
if [ -n "${1:-}" ]; then
    echo "$1" > "$ERPDIR/backend/.env"
    echo ".env 已更新 ✓"
else
    echo "警告: 未收到 .env 内容，使用现有配置"
fi

# ── 2. 安装/更新 Python 依赖 ─────────────────────────
echo "[1/3] 更新 Python 依赖..."
source "$ERPDIR/backend/venv/bin/activate"
pip install -q -r "$ERPDIR/backend/requirements.txt"
deactivate

# ── 3. 重启后端服务 ───────────────────────────────────
echo "[2/3] 重启后端服务..."
systemctl daemon-reload
systemctl restart erp-server
echo "后端已重启 ✓"

# ── 4. 验证服务健康 ───────────────────────────────────
echo "[3/3] 验证服务..."
sleep 2
if curl -sf http://127.0.0.1:8000/docs > /dev/null 2>&1; then
    echo "后端健康检查通过 ✓"
else
    echo "警告: 后端未响应，请检查日志"
    journalctl -u erp-server --no-pager -n 20
fi

echo "===== 部署完成 ====="

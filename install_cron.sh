#!/usr/bin/env bash
# rime-aisync 定时任务安装脚本 (Armbian / Linux)

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PYTHON_BIN="$(which python3)"
CONFIG_PATH="${SCRIPT_DIR}/config.json"

if [ -z "$PYTHON_BIN" ]; then
    echo "错误: 未找到 python3 命令，请先安装 Python 3。"
    exit 1
fi

echo "=========================================="
echo "Installing Cron jobs for rime-aisync..."
echo "Script Path: ${SCRIPT_DIR}"
echo "Python Executable: ${PYTHON_BIN}"
echo "=========================================="

CRON_INC="30 12,18 * * * ${PYTHON_BIN} ${SCRIPT_DIR}/main.py --config ${CONFIG_PATH} --mode incremental >> /var/log/rime_aisync_inc.log 2>&1"
CRON_DEEP="0 3 * * * ${PYTHON_BIN} ${SCRIPT_DIR}/main.py --config ${CONFIG_PATH} --mode deep >> /var/log/rime_aisync_deep.log 2>&1"

# 读取当前用户的 cron
(crontab -l 2>/dev/null | grep -v "${SCRIPT_DIR}/main.py") > /tmp/current_crontab

# 追加新的定时任务
echo "# Rime AI Sync Incremental (Daytime 12:30 & 18:30)" >> /tmp/current_crontab
echo "${CRON_INC}" >> /tmp/current_crontab

echo "# Rime AI Sync Deep (Nighttime 03:00)" >> /tmp/current_crontab
echo "${CRON_DEEP}" >> /tmp/current_crontab

# 应用新 cron
crontab /tmp/current_crontab
rm -f /tmp/current_crontab

echo "✅ 定时任务安装完毕！"
echo "白天增量任务: 每天 12:30, 18:30"
echo "晚间深度任务: 每天 03:00"
echo "运行日志输出至: /var/log/rime_aisync_*.log"

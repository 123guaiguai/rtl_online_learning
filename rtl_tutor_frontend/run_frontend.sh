#!/bin/bash

# Terminate on error
set -e

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0;0m'

echo -e "${YELLOW}正在启动 RTL-Tutor 前端服务...${NC}"

# Check Conda environment
if ! conda env list | grep -q "autochip"; then
    echo -e "${RED}错误: autochip conda 环境不存在${NC}"
    exit 1
fi

# Get current script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "${SCRIPT_DIR}"

# Unset proxies to avoid local loopback issues
unset http_proxy https_proxy all_proxy

# Launch the dev server
echo -e "${GREEN}启动 Vite 开发服务器 (监听端口 5173)...${NC}"
conda run --no-capture-output -n autochip npm run dev -- --host 0.0.0.0

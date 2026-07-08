#!/bin/bash

# Terminate on error
set -e

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0;0m'

echo -e "${YELLOW}正在启动 RTL-Tutor 后端服务...${NC}"

# Check Conda environment
if ! conda env list | grep -q "autochip"; then
    echo -e "${RED}错误: autochip conda 环境不存在${NC}"
    echo "请先运行: conda create -n autochip python=3.10 -y"
    exit 1
fi

# Get current script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
BACKEND_DIR="${SCRIPT_DIR}/core"

# Navigate to core folder containing web_backend.py
cd "${BACKEND_DIR}"

# Unset proxies if set to avoid network loopbacks
unset http_proxy https_proxy all_proxy

# Launch the FastAPI app under docker group privileges so it can create sandboxed containers
echo -e "${GREEN}启动 FastAPI 后端，监听端口 8000 (使用 Docker 用户组)...${NC}"
sg docker -c "conda run --no-capture-output -n autochip python -m uvicorn web_backend:app --host 0.0.0.0 --port 8000 --reload"

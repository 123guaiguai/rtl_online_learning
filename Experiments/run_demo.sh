#!/bin/bash
# AutoChip 快速启动脚本
# 用法: ./run_demo.sh [test_case] [model]

set -e

# 默认参数
TEST_CASE=${1:-"rule90"}
MODEL=${2:-"siliconflow"}

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Experiments 快速启动${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查 conda 环境
if ! conda env list | grep -q "autochip"; then
    echo -e "${RED}错误: autochip conda 环境不存在${NC}"
    echo "请先运行: conda create -n autochip python=3.10 -y"
    exit 1
fi

# 激活环境
echo -e "${YELLOW}激活 conda 环境...${NC}"
source $(conda info --base)/etc/profile.d/conda.sh
conda activate autochip

# 设置 API Key
export OPENAI_API_KEY="sk-eafwjcjcwpdrnhykbqnxgtytkwiopatluswkhvmhbyktxcxp"

# 取消代理（避免网络问题）
unset http_proxy https_proxy all_proxy

# 进入工作目录（使用脚本自身位置的相对路径，无需硬编码绝对路径）
cd "$(dirname "$0")/core"

# 选择配置文件
if [ "$MODEL" == "siliconflow" ]; then
    CONFIG="configs/config_siliconflow.json"
    echo -e "${YELLOW}使用模型: Siliconflow (Qwen/Qwen2.5-Coder-32B-Instruct)${NC}"
elif [ "$MODEL" == "github" ]; then
    # 需要创建 github 配置文件
    CONFIG="configs/config_github.json"
    echo -e "${YELLOW}使用模型: GitHub Models (gpt-4o-mini)${NC}"
else
    echo -e "${RED}错误: 不支持的模型类型 '$MODEL'${NC}"
    echo "支持的模型: siliconflow, github"
    exit 1
fi

# 检查测试用例文件
PROMPT_FILE="../verilogeval_prompts_tbs/validation_set/${TEST_CASE}/${TEST_CASE}.sv"
TB_FILE="../verilogeval_prompts_tbs/validation_set/${TEST_CASE}/${TEST_CASE}_tb.sv"

if [ ! -f "$PROMPT_FILE" ]; then
    echo -e "${RED}错误: 找不到提示词文件 $PROMPT_FILE${NC}"
    exit 1
fi

if [ ! -f "$TB_FILE" ]; then
    echo -e "${RED}错误: 找不到测试平台文件 $TB_FILE${NC}"
    exit 1
fi

echo -e "${YELLOW}测试用例: ${TEST_CASE}${NC}"
echo -e "${YELLOW}提示词文件: ${PROMPT_FILE}${NC}"
echo -e "${YELLOW}测试平台: ${TB_FILE}${NC}"
echo ""

# 创建输出目录
OUTPUT_DIR="outputs/output_${TEST_CASE}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_DIR"

# 更新配置文件中的输出目录
python3 << EOF
import json
with open('${CONFIG}', 'r') as f:
    config = json.load(f)
config['general']['prompt'] = '../verilogeval_prompts_tbs/validation_set/${TEST_CASE}/${TEST_CASE}.sv'
config['general']['name'] = 'top_module'
config['general']['testbench'] = '../verilogeval_prompts_tbs/validation_set/${TEST_CASE}/${TEST_CASE}_tb.sv'
config['general']['outdir'] = '${OUTPUT_DIR}'
config['general']['log'] = 'log.txt'
with open('${CONFIG}', 'w') as f:
    json.dump(config, f, indent=4)
EOF

echo -e "${YELLOW}开始生成 Verilog 代码...${NC}"
echo -e "${GREEN}----------------------------------------${NC}"

# 运行 AutoChip
python generate_verilog.py -c "$CONFIG"

echo -e "${GREEN}----------------------------------------${NC}"
echo ""
echo -e "${GREEN}✅ 生成完成！${NC}"
echo ""
echo -e "${YELLOW}输出目录: ${OUTPUT_DIR}${NC}"
echo -e "${YELLOW}日志文件: ${OUTPUT_DIR}/log.txt${NC}"
echo ""

# 显示生成的代码
GENERATED_CODE=$(find "$OUTPUT_DIR" -name "top_module.sv" | head -1)
if [ -f "$GENERATED_CODE" ]; then
    echo -e "${YELLOW}生成的 Verilog 代码:${NC}"
    echo -e "${GREEN}----------------------------------------${NC}"
    cat "$GENERATED_CODE"
    echo -e "${GREEN}----------------------------------------${NC}"
fi

echo ""
echo -e "${GREEN}🎉 所有任务完成！${NC}"

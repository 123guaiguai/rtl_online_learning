# Experiments — LLM 驱动的 Verilog 代码自动生成框架

本项目基于开源框架 [AutoChip](https://github.com/shailja-thakur/AutoChip) 二次开发，通过大语言模型（LLM）与 EDA 仿真工具（Icarus Verilog）的紧密配合，实现 Verilog 代码的**自动生成 → 编译验证 → 错误反馈 → 迭代修复**的闭环流水线。

---

## 快速上手

```bash
# 1. 激活环境
conda activate autochip

# 2. 配置 API 密钥（首次使用）
cd Experiments
cp api_keys.example.py api_keys.py
# 编辑 api_keys.py，填入真实密钥

# 3. 快速运行单道题验证
./run_demo.sh rule90 siliconflow

# 4. 批量测试（进入脚本目录后运行）
cd core
conda run -n autochip python run_batch_experiments.py -g hard -l 5 -i 2 -k 2 -n quick_test
```

---

## 项目文档

详细文档位于 [`docs/`](docs/) 目录：

| 文档 | 内容 |
|------|------|
| [01_项目简介与结构说明.md](docs/01_项目简介与结构说明.md) | 项目背景、整体目录结构、核心运行机制（迭代、Rank 评分、候选机制、混合模型） |
| [02_常规使用与部署指南.md](docs/02_常规使用与部署指南.md) | 环境安装、API 密钥配置、单题运行、配置文件说明、常见问题排查 |
| [03_批量测试与扩展指南.md](docs/03_批量测试与扩展指南.md) | 批量测试命令行参数、示例运行命令、输出目录结构、混合模型策略、结果分析工具 |

---

## 核心依赖

- **Python 3.10**（Conda 环境 `autochip`）
- **Icarus Verilog**（`iverilog` / `vvp`）
- **openai / anthropic / google-generativeai**

---

## 目录结构速览

```
Autochip_workspace/
├── Experiments/
│   ├── core/          ← 核心代码
│   │   ├── generate_verilog.py    ← 单题入口
│   │   ├── run_batch_experiments.py ← 批量测试唯一入口
│   │   └── ...
│   ├── VerilogEval/               ← 测试题数据集
│   ├── api_keys.py      ← 密钥配置（本地，不提交 Git）
│   └── run_demo.sh                ← 快速验证脚本
└── docs/                          ← 项目文档
```

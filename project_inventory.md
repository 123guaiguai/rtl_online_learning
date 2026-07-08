# Autochip 衍生项目结构资源清单

本项目基于原始的 AutoChip 框架进行二次开发，增加了一系列为了提升 LLM 生成 Verilog 代码质量而设计的批量测试、模型混合以及效果分析工具。由于经历了多个开发阶段，项目结构包含了原版代码、二次开发脚本以及大量的记录文档。

以下是整个项目的梳理分类清单。

---

## 1. 核心运行模块 (`AutoChip/autochip_scripts/`)
此目录是整个项目的**“大脑”**，包含了原版框架以及二次开发注入的各项核心运行脚本。

### **1.1 核心主流程代码 (基于原版改造)**
* `generate_verilog.py`：单题生成主入口，接收 `config_*.json` 配置，串联整个迭代生成与仿真验证流程。
* `config_handler.py`：配置文件解析器，读取并解析用户提供的配置信息。
* `languagemodels.py`：大语言模型（LLM）的接口集合。二次开发中增加了对多种现代模型（如 Siliconflow 的 Qwen、GitHub Models 的 gpt-4o-mini 等）的安全、动态密钥加载逻辑。
* `verilog_handling.py`：代码提纯与仿真测试的核心。负责清理 LLM 的输出、提取 Verilog 代码并调用 iVerilog 编译仿真。
* `conversation.py`：消息追踪与维护工具，存储提示词与多轮对话的历史。
* `parse_data.py` & `parse_parameter_sweep.py`：原版提供的数据解析工具（通常用于处理模型实验输出）。
* `tools.py` & `utils.py`：原版的杂项工具类库。

### **1.2 批量测试与流水线 (二次开发新增)**
* `batch_test.py`：硬编码的批量测试骨架。负责将 VerilogEval 数据集分为“简单组(0-50)”和“困难组(50-100)”，可引入诸如“前几次用小模型、后几次用大模型”的**混合模型验证机制**。
* `run_batch_experiments.py`：带参数化接口的批量测试脚本。在 `batch_test.py` 的基础上封装了更优雅的命令行接口（CLI），支持外部自由调整生成候选（candidates）、迭代次数（iterations）以及起止题号。
* `run_batch_test.sh`：批量测试的后台保活运行脚本（支持防 SSH 断连）。
* `analyze_batch_results.py`：结果分析工具，运行在批量测试结束后，自动汇总所有输出 `log.txt` 数据并生成图文并茂的 Markdown 统计报告。

### **1.3 核心附属资产**
* `configs/`（文件夹）：存放各次运行中使用的 JSON 配置模板，例如 `config_siliconflow.json`。
* `outputs/`（文件夹）：所有的日志、JSON 结果、中间代码与验证波形的输出目录。
* `api_keys.env`：二次开发中尝试用来隔离 API 密钥的备份文件（目前已被 `.autochip_api_keys.py` 机制替代）。

---

## 2. 数据集与仿真驱动
负责提供题目源和验证其正确性的测试平台。

### **2.1 `AutoChip/VerilogEval/` (核心二次开发用例)**
* 存放从 VerilogEval 数据集中清洗处理后的测试集合，通常表现为 `ProbXXX_prompt.txt`（题目）和 `ProbXXX_test.sv`（测试台文件），也是 `batch_test.py` 强依赖的数据读取目录。

### **2.2 `AutoChip/verilogeval_prompts_tbs/` (原版用例备份区)**
* `*.jsonl`：各类开源提示集和基准测试题目数据的原生文件。
* `validation_set/`、`ve_testbenches_human/`、`ve_testbenches_machine/`：不同规模和来源的测试平台集散地。
* `extract_tbs.py` & `check_dirs.py`：原版中用于从 jsonl 中解包/整理出 `.sv` 和 `.txt` 文件的 Python 辅助脚本。

---

## 3. 全局入口与脚手架 (`/` 和 `AutoChip/`)
提供快速上手和部署打包支持。

* `AutoChip/run_demo.sh`：面向新手的快速验证脚本，用于验证 Conda 环境以及测试单道题。
* `AutoChip/.autochip_api_keys.py` & `.autochip_api_keys.example.py`：密钥安全隔离文件，避免敏感数据随 Git 泄露。
* `setup_for_github.sh`：上传 GitHub 的打包前准备脚本，清除冗余日志、替换敏感密钥配置并重整文件。
* `upload_to_github.sh`：自动化执行 git add/commit/push，保证提交前的代码与密钥安全检查机制。
* `AutoChip/requirements.txt`：项目 Python 依赖项（主要是 `openai`, `anthropic`, `google-generativeai` 等）。

---

## 4. 文档库 (`docs/`)
二次开发留下的大量记录文件。这些文档记载了各种尝试、经验与技术架构决策。

* **基础认知类**
  * `AutoChip_CORE_CONCEPTS.md` / `核心机制详解.md`：深入介绍了 AutoChip 错误反馈循环、大模型处理机制的实现逻辑。
  * `project_architecture_report.md`：本项目的架构概览设计报告。
* **快速使用指南类**
  * `QUICKSTART.md`：框架起步指南。
  * `QUICK_START_SECURITY.md` / `API_KEYS_SECURITY_GUIDE.md`：如何保证你在开发与上传过程中保护 API Key 不受泄露的安全守则。
  * `批量测试使用指南.md` / `BATCH_EXPERIMENTS_GUIDE.md` / `参数化批量测试快速参考.md`：教授如何使用新写的批量测试组件 `run_batch_experiments.py` 进行数据刷榜。
  * `混合模型批量测试指南.md`：特指如何设置多模型接力迭代的指南。
* **问题与解决报告类**
  * `VerilogEval兼容性适配报告.md`：二次开发中，针对 VerilogEval 题目不兼容导致的编译 Bug（如参考模块缺失问题）进行修复的心得汇总。
  * `Siliconflow_Token计费修复报告.md`：关于 SiliconFlow 平台接口特殊行为了解与处理。
  * `AutoChip_DEPLOYMENT_REPORT.md`：运行环境部署记录。
  * `批量测试总结报告_*.md`：跑分测试的归档总结日志。

---

## 5. 其他
* `papers/` 及其子目录 `figs/`：原项目留存的资料（例如 `paper1.mmd` 等论文/架构图材料）。
* `GITHUB_UPLOAD_GUIDE.md` & `PROJECT_SUMMARY.md`：关于向 Github 发行的指导规范。

### 📌 给未来开发的建议
可以看出这个项目经过了“原版搭建 -> 小范围跑通 -> 引入批量跑分流水线 -> 安全与兼容性重构” 等阶段。如果在接下来的使用中想让项目更整洁，建议以目前的 `AutoChip/autochip_scripts/` 作为主核心目录（可将其更名为 `core` 避免冗长），将所有说明文档集中移至根目录的 `docs` 里统一维护。

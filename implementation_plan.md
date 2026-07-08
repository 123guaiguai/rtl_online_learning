# 自动芯片环境清理与优化实施计划

本项目包含较多开发阶段遗留的文件，此计划将按照要求对代码结构、文档和多余配置进行精简，以提升项目的可读性和维护性。

## Proposed Changes

### 1. 批量测试核心整合 (AutoChip/autochip_scripts)
将原有的 `batch_test.py` 的核心函数与配置（分组信息、创建单题配置文件、检测完成状态、启动仿真测试等）直接合并入带参数化接口的 `run_batch_experiments.py` 中。确保项目只有一个统一、标准且支持参数调节的批量测试主入口。

#### [MODIFY] [run_batch_experiments.py](file:///home/gq/Autochip_workspace/AutoChip/autochip_scripts/run_batch_experiments.py)
合并代码，将依赖独立文件解除。

#### [DELETE] [batch_test.py](file:///home/gq/Autochip_workspace/AutoChip/autochip_scripts/batch_test.py)
#### [DELETE] [run_batch_test.sh](file:///home/gq/Autochip_workspace/AutoChip/autochip_scripts/run_batch_test.sh)

---

### 2. 清理遗留配置与 Github 上传脚手架
鉴于我们已经采用了 `.autochip_api_keys.py` 来处理敏感数据并无需再次使用相关打包上传脚本，删除以下冗余文件：

#### [DELETE] [api_keys.env](file:///home/gq/Autochip_workspace/AutoChip/autochip_scripts/api_keys.env)
#### [DELETE] [setup_for_github.sh](file:///home/gq/Autochip_workspace/setup_for_github.sh)
#### [DELETE] [upload_to_github.sh](file:///home/gq/Autochip_workspace/upload_to_github.sh)

---

### 3. 文档体系重构与整合 (docs 目录)
将分散在根目录和 `docs/` 下近20个零散的说明、报告、指南，精炼并合并为 3 个结构化、具有良好排版的中文核心文档。

#### [NEW] [01_项目简介与结构说明.md](file:///home/gq/Autochip_workspace/docs/01_项目简介与结构说明.md)
汇总核心机制、项目架构设计报告以及输出目录结构详解。

#### [NEW] [02_常规使用与部署指南.md](file:///home/gq/Autochip_workspace/docs/02_常规使用与部署指南.md)
汇总快速启动、环境配置、API Key配置安全指引。

#### [NEW] [03_批量测试与扩展指南.md](file:///home/gq/Autochip_workspace/docs/03_批量测试与扩展指南.md)
汇总混合模型测试、参数化指令用法、错误解决报告。

#### [MODIFY] [README.md](file:///home/gq/Autochip_workspace/README.md)
将其简化为一个入口面板，提供指向 `docs/` 下这 3 个新文档的链接。

#### [DELETE] 现存旧版文档
删除如 `PROJECT_SUMMARY.md`, `GITHUB_UPLOAD_GUIDE.md`, `docs/AutoChip_CORE_CONCEPTS.md`, `docs/参数化批量测试快速参考.md` 等所有零散的旧 Markdown 文件。

## User Review Required

> [!WARNING]  
> 该计划将**彻底删除**近 15 个以上的旧版 Markdown 记录文件，并用三个综合文档取而代之。如果您有需要单独留档的内容，请注意提前备份。同意后我将开始实施合并和清理。

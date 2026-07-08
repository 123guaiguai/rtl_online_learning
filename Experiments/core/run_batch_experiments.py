#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoChip 参数化批量测试工具（唯一批量测试入口）

支持命令行参数控制所有实验配置，无需修改代码。

功能：
1. 将 VerilogEval 测试集分为简单组（0-50题）和困难组（50-100题）两组
2. 每组独立运行，支持断点续传
3. 通过参数灵活控制迭代次数、候选数量、是否启用混合模型
4. 详细统计日志记录通过率

用法示例：
  python run_batch_experiments.py -g hard -l 5 -i 2 -k 2 -n my_exp
  python run_batch_experiments.py -g all --no-mixed-models -n baseline
"""

import os
import sys
import json
import argparse
import subprocess
import time
import glob
import re
import copy
from datetime import datetime
from pathlib import Path

# ============================================================
# 全局配置
# ============================================================

# VerilogEval 数据集目录（相对于本脚本目录）
VERILOG_EVAL_DIR = "../VerilogEval"

# 批量测试输出目录（相对于本脚本目录）
OUTPUT_BASE_DIR = "outputs/batch_tests"

# 每个迭代生成的候选代码数量（可通过 -k 参数覆盖）
NUM_CANDIDATES = 3

# 分组配置（不同组使用不同的迭代次数和模型策略）
GROUP_CONFIGS = {
    "easy": {
        "range": (0, 50),
        "max_iterations": 2,      # 简单组：共尝试 3 次（iter0, iter1, iter2）
        "use_mixed_models": False,
        "model_family": "Siliconflow",
        "model_id": "Qwen/Qwen2.5-Coder-32B-Instruct"
    },
    "hard": {
        "range": (50, 100),
        "max_iterations": 5,      # 困难组：执行 iter0-iter4，iter5 使用第二模型
        "use_mixed_models": True,
        "mixed_models": {
            "model1": {
                "start_iteration": 0,
                "model_family": "Siliconflow",
                "model_id": "Qwen/Qwen2.5-Coder-32B-Instruct"
            },
            "model2": {
                "start_iteration": 5,         # 第 6 次迭代（iter5）使用 GPT-4o-mini
                "model_family": "ChatGPT",
                "model_id": "gpt-4o-mini",
                "base_url": "https://models.inference.ai.azure.com"
            }
        }
    }
}


# ============================================================
# 数据集与配置工具函数（原 batch_test.py 核心逻辑）
# ============================================================

def get_problem_list():
    """获取 VerilogEval 目录中所有测试题目列表"""
    prompt_files = sorted(glob.glob(os.path.join(VERILOG_EVAL_DIR, "Prob*_prompt.txt")))
    problems = []
    for pf in prompt_files:
        basename = os.path.basename(pf)
        # 提取题目ID，如 Prob001_zero_prompt.txt -> Prob001_zero
        prob_id = basename.replace("_prompt.txt", "")
        problems.append(prob_id)

    print(f"📋 找到 {len(problems)} 道题目")
    if problems:
        print(f"   第一题: {problems[0]}")
        print(f"   最后一题: {problems[-1]}")

    return problems


def create_config_for_problem(prob_id, output_dir, group_name):
    """为单个题目动态生成 JSON 配置文件"""
    if group_name not in GROUP_CONFIGS:
        raise ValueError(f"未知的分组名称: {group_name}")

    group_cfg = GROUP_CONFIGS[group_name]

    general_config = {
        "prompt": f"{VERILOG_EVAL_DIR}/{prob_id}_prompt.txt",
        "name": "TopModule",
        "testbench": f"{VERILOG_EVAL_DIR}/{prob_id}_test.sv",
        "model_family": group_cfg.get("model_family", "Siliconflow"),
        "model_id": group_cfg.get("model_id", ""),
        "num_candidates": NUM_CANDIDATES,
        "iterations": group_cfg["max_iterations"],
        "outdir": output_dir,
        "log": "log.txt",
        "mixed-models": group_cfg.get("use_mixed_models", False)
    }

    config_data = {"general": general_config}

    if group_cfg.get("use_mixed_models", False) and "mixed_models" in group_cfg:
        config_data["mixed-models"] = group_cfg["mixed_models"]
    else:
        config_data["mixed-models"] = {}

    os.makedirs("configs", exist_ok=True)
    config_file = f"configs/config_{prob_id}.json"
    with open(config_file, 'w') as f:
        json.dump(config_data, f, indent=4)

    return config_file


def check_if_completed(output_dir):
    """
    检查某道题目是否已完成测试（用于断点续传）

    通过读取 output_dir/log.txt 中的 Rank 信息来判断。
    Returns:
        tuple: (completed: bool, rank: float or None)
    """
    main_log = os.path.join(output_dir, "log.txt")

    if not os.path.exists(main_log):
        return False, None

    try:
        with open(main_log, 'r') as f:
            content = f.read()

            rank_match = re.search(r'Rank of best response:\s*([-\d.]+)', content)
            if rank_match:
                return True, float(rank_match.group(1))

            rank_match = re.search(r'Best.*Rank:\s*([-\d.]+)', content)
            if rank_match:
                return True, float(rank_match.group(1))

            rank_match = re.search(r'Final Rank:\s*([-\d.]+)', content)
            if rank_match:
                return True, float(rank_match.group(1))

            if "Iteration:" in content:
                return False, None  # 已开始但未完成

    except Exception as e:
        print(f"⚠️ 读取日志文件失败 {main_log}: {e}")

    return False, None


def run_single_test(prob_id, config_file, output_dir):
    """
    运行单道题的生成+评测流程

    Returns:
        float: rank（1.0=通过，0~1=部分通过，负数=错误）
    """
    print(f"\n{'='*60}")
    print(f"🧪 测试: {prob_id}")
    print(f"{'='*60}")

    # 断点续传：已完成则跳过
    completed, rank = check_if_completed(output_dir)
    if completed:
        status = "✅ PASS" if rank == 1.0 else "❌ FAIL"
        print(f"⏭️  跳过（已完成）: {status} (Rank: {rank})")
        return rank

    cmd = ["python", "generate_verilog.py", "-c", config_file]
    print(f"🚀 开始测试...")
    start_time = time.time()

    try:
        env = os.environ.copy()
        # 清理所有代理设置，避免 SOCKS 代理干扰
        for proxy_var in ['http_proxy', 'https_proxy', 'all_proxy',
                          'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
            env.pop(proxy_var, None)

        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=600
        )
        elapsed = time.time() - start_time

        if result.returncode != 0:
            print(f"❌ 执行失败 (返回码: {result.returncode})")
            if result.stderr:
                print(f"错误信息: {result.stderr[:500]}")
            return -1

        completed, rank = check_if_completed(output_dir)
        if completed:
            status = "✅ PASS" if rank == 1.0 else "❌ FAIL"
            print(f"✅ 完成 ({elapsed:.1f}s): {status} (Rank: {rank})")
            return rank
        else:
            print(f"❌ 完成但未找到结果")
            return -1

    except subprocess.TimeoutExpired:
        print(f"⏰ 超时 (>10分钟)")
        return -2
    except Exception as e:
        print(f"❌ 异常: {e}")
        return -3


# ============================================================
# 参数化实验控制函数
# ============================================================

def load_env_config(env_file):
    """从 .env 格式的文本文件中加载键值对作为环境变量"""
    if not os.path.exists(env_file):
        print(f"Warning: env file not found: {env_file}")
        return {}

    env_vars = {}
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                value = value.strip('"').strip("'")
                env_vars[key.strip()] = value
    return env_vars


def setup_environment(env_file=None, api_keys=None):
    """初始化运行环境：清理代理，可选地从文件或参数加载环境变量"""
    for var in ['http_proxy', 'https_proxy', 'all_proxy',
                'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
        os.environ.pop(var, None)

    if env_file:
        env_vars = load_env_config(env_file)
        for key, value in env_vars.items():
            os.environ[key] = value
        print(f"[OK] Loaded environment variables from: {env_file}")

    if api_keys:
        for key, value in api_keys.items():
            os.environ[key] = value
        print(f"[OK] Set API Keys from command line")


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='AutoChip 参数化批量测试工具（唯一批量测试入口）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 测试困难组前5题，迭代2次，2个候选
  python run_batch_experiments.py -g hard -l 5 -i 2 -k 2 -n quick_test

  # 测试所有题目（简单+困难），禁用混合模型
  python run_batch_experiments.py -g all --no-mixed-models -n baseline

  # 预演（不实际运行，仅检查配置）
  python run_batch_experiments.py -g hard -l 3 --dry-run
        """
    )
    parser.add_argument('--group', '-g', choices=['easy', 'hard', 'all'], default='hard',
                        help='测试分组: easy(0-50), hard(50-100), all(全部) [默认: hard]')
    parser.add_argument('--limit', '-l', type=int, default=None,
                        help='每组最多测试题目数（用于快速验证）')
    parser.add_argument('--iterations', '-i', type=int, default=None,
                        help='每道题的最大迭代次数（覆盖默认配置）')
    parser.add_argument('--candidates', '-k', type=int, default=None,
                        help='每次迭代生成的候选代码数量')
    parser.add_argument('--mixed-models', '-m', action='store_true', default=None,
                        help='强制启用混合模型策略')
    parser.add_argument('--no-mixed-models', action='store_true',
                        help='强制禁用混合模型策略')
    parser.add_argument('--gpt-start-iter', type=int, default=None,
                        help='混合模型中第二个模型从第几次迭代开始介入')
    parser.add_argument('--output-dir', '-o', type=str, default=None,
                        help='批量测试结果输出目录')
    parser.add_argument('--experiment-name', '-n', type=str, default=None,
                        help='实验名称（用于输出目录命名）')
    parser.add_argument('--overwrite', action='store_true',
                        help='覆盖已存在的输出目录（默认为断点续传模式）')
    parser.add_argument('--env-file', '-e', type=str, default=None,
                        help='从指定 .env 文件加载环境变量')
    parser.add_argument('--api-key', action='append', nargs=2, metavar=('KEY', 'VALUE'),
                        help='通过命令行设置环境变量，如 --api-key OPENAI_API_KEY sk-xxx')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='输出详细调试信息')
    parser.add_argument('--dry-run', action='store_true',
                        help='预演模式：仅显示配置，不实际运行测试')

    return parser.parse_args()


def generate_output_path(base_dir, group_name, experiment_name=None, overwrite=False):
    """生成带时间戳的输出目录路径"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if experiment_name:
        if group_name in experiment_name:
            dir_name = f"{experiment_name}_{timestamp}"
        else:
            dir_name = f"{experiment_name}_{group_name}_{timestamp}"
    else:
        dir_name = f"{group_name}_{timestamp}"

    output_path = os.path.join(base_dir, dir_name)

    if os.path.exists(output_path):
        if overwrite:
            print(f"Warning: Output directory exists, will overwrite: {output_path}")
            import shutil
            shutil.rmtree(output_path)
        else:
            completed = len([d for d in os.listdir(output_path)
                             if os.path.isdir(os.path.join(output_path, d))])
            print(f"Info: Found existing output directory, resuming (completed {completed} problems)")

    os.makedirs(output_path, exist_ok=True)
    return output_path


def modify_group_config(group_name, config_updates):
    """根据命令行参数动态修改分组配置（不影响原始全局配置）"""
    modified_config = copy.deepcopy(GROUP_CONFIGS[group_name])

    if 'max_iterations' in config_updates:
        modified_config['max_iterations'] = config_updates['max_iterations']

    if 'use_mixed_models' in config_updates:
        modified_config['use_mixed_models'] = config_updates['use_mixed_models']
        if not config_updates['use_mixed_models'] and 'mixed_models' in modified_config:
            model1 = modified_config['mixed_models'].get('model1', {})
            if 'model_family' in model1:
                modified_config['model_family'] = model1['model_family']
            if 'model_id' in model1:
                modified_config['model_id'] = model1['model_id']

    if 'mixed_models' in config_updates and config_updates['mixed_models']:
        mixed_cfg = config_updates['mixed_models']
        if 'model2' in modified_config.get('mixed_models', {}):
            if 'start_iteration' in mixed_cfg:
                modified_config['mixed_models']['model2']['start_iteration'] = mixed_cfg['start_iteration']

    return modified_config


def run_experiment(config):
    """执行完整批量测试实验"""
    print("=" * 80)
    print("AutoChip 参数化批量测试")
    print("=" * 80)
    print()

    setup_environment(config['env_file'], config['api_keys'])
    print()

    groups_to_test = ['easy', 'hard'] if config['group'] == 'all' else [config['group']]
    all_problems = get_problem_list()

    for group_name in groups_to_test:
        print(f"\n准备测试分组: {group_name.upper()}")

        if group_name == 'easy':
            group_problems = [p for p in all_problems if p.startswith('Prob0') and int(p[4:7]) < 50]
        elif group_name == 'hard':
            group_problems = [p for p in all_problems if p.startswith('Prob0') and int(p[4:7]) >= 50]
        else:
            group_problems = all_problems

        if config['limit']:
            group_problems = group_problems[:config['limit']]
            print(f"小规模测试模式：仅测试前 {config['limit']} 道题")

        print(f"题目数量: {len(group_problems)}")

        output_base = generate_output_path(
            config['output_dir'], group_name, config['experiment_name'], config['overwrite']
        )
        print(f"输出目录: {output_base}")

        # 构建分组配置覆盖项
        group_config_updates = {}
        if config['iterations'] is not None:
            group_config_updates['max_iterations'] = config['iterations']

        if config['mixed_models'] is not None:
            group_config_updates['use_mixed_models'] = config['mixed_models']
        elif config['disable_mixed_models']:
            group_config_updates['use_mixed_models'] = False

        if config['gpt_start_iter'] is not None:
            group_config_updates['mixed_models'] = {'start_iteration': config['gpt_start_iter']}

        # 保存原始配置，运行后恢复（避免多组运行时配置污染）
        original_config = copy.deepcopy(GROUP_CONFIGS[group_name])
        original_candidates = NUM_CANDIDATES

        modified_config = modify_group_config(group_name, group_config_updates)
        GROUP_CONFIGS[group_name] = modified_config

        current_candidates = config['candidates'] if config['candidates'] is not None else NUM_CANDIDATES

        print(f"\n当前实验配置:")
        print(f"  - 迭代次数: {modified_config['max_iterations']} (共尝试 {modified_config['max_iterations']+1} 次)")
        print(f"  - 候选数量: {current_candidates}")
        print(f"  - 混合模型: {'已启用' if modified_config.get('use_mixed_models') else '已禁用'}")
        print()

        if config['dry_run']:
            print("预演模式，跳过实际测试\n")
            GROUP_CONFIGS[group_name] = original_config
            continue

        results = []
        passed = failed = errors = skipped = 0
        start_time = time.time()

        # 临时覆盖全局 NUM_CANDIDATES（通过重写 create_config_for_problem 内部引用）
        global NUM_CANDIDATES
        if config['candidates'] is not None:
            NUM_CANDIDATES = config['candidates']

        for i, prob_id in enumerate(group_problems, 1):
            print(f"\n[{i}/{len(group_problems)}] ", end="")

            prob_output_dir = os.path.join(output_base, prob_id)

            # 断点续传：检查是否已有完成记录
            log_file = os.path.join(prob_output_dir, "log.txt")
            if os.path.exists(log_file) and not config['overwrite']:
                try:
                    with open(log_file, 'r') as f:
                        if "Rank of best response:" in f.read():
                            print(f"跳过（已完成）")
                            skipped += 1
                            continue
                except Exception:
                    pass

            os.makedirs(prob_output_dir, exist_ok=True)
            config_file = create_config_for_problem(prob_id, prob_output_dir, group_name)
            rank = run_single_test(prob_id, config_file, prob_output_dir)

            results.append({'problem': prob_id, 'rank': rank})

            if rank == 1.0:
                passed += 1
            elif rank >= 0:
                failed += 1
            else:
                errors += 1

        # 恢复全局配置
        NUM_CANDIDATES = original_candidates
        GROUP_CONFIGS[group_name] = original_config

        elapsed = time.time() - start_time
        total = len(group_problems)
        pass_rate = (passed / total * 100) if total > 0 else 0

        print(f"\n{'='*80}")
        print(f"{group_name.upper()} 分组测试结果")
        print(f"{'='*80}")
        print(f"总题数:   {total}")
        print(f"通过:     {passed} ✅")
        print(f"失败:     {failed} ❌")
        print(f"跳过:     {skipped} ⏭️")
        print(f"错误:     {errors} ⚠️")
        print(f"通过率:   {pass_rate:.2f}%")
        print(f"耗时:     {elapsed:.1f}s ({elapsed/60:.1f}min)")
        print(f"{'='*80}")

        # 保存 JSON 结果文件
        result_file = os.path.join(output_base, f"results_{group_name}.json")
        result_data = {
            'timestamp': datetime.now().isoformat(),
            'group': group_name,
            'config': {
                'iterations': modified_config['max_iterations'],
                'candidates': current_candidates,
                'mixed_models': modified_config.get('use_mixed_models', False),
            },
            'statistics': {
                'total': total, 'passed': passed, 'failed': failed,
                'skipped': skipped, 'errors': errors,
                'pass_rate': round(pass_rate, 2),
                'elapsed_seconds': round(elapsed, 1),
            },
            'details': results
        }

        with open(result_file, 'w') as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)

        print(f"\n结果已保存至: {result_file}")

    print("\n所有测试完成！")


def main():
    args = parse_args()
    config = {
        'group': args.group,
        'limit': args.limit,
        'iterations': args.iterations,
        'candidates': args.candidates,
        'mixed_models': args.mixed_models,
        'disable_mixed_models': args.no_mixed_models,
        'gpt_start_iter': args.gpt_start_iter,
        'output_dir': args.output_dir or OUTPUT_BASE_DIR,
        'experiment_name': args.experiment_name,
        'overwrite': args.overwrite,
        'env_file': args.env_file,
        'api_keys': dict(args.api_key) if args.api_key else {},
        'verbose': args.verbose,
        'dry_run': args.dry_run,
    }

    run_experiment(config)


if __name__ == '__main__':
    main()

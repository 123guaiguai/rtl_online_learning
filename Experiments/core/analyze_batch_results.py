#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoChip 批量测试结果分析与报告生成工具
支持从JSON结果文件和日志文件中提取结构化信息，生成多维度统计报告

使用示例：
1. 分析单个实验（控制台输出）：
   python analyze_batch_results.py --result-dir outputs/batch_tests/hard_20260414_100241

2. 分析单个实验并显示详细信息：
   python analyze_batch_results.py --result-dir outputs/batch_tests/hard_20260414_100241 --verbose

3. 生成Markdown报告：
   python analyze_batch_results.py --result-dir outputs/batch_tests/hard_20260414_100241 \
       --output-format markdown --output-file report.md

4. 对比多个实验：
   python analyze_batch_results.py --batch-dir outputs/batch_tests/ --compare

5. 生成JSON格式的结构化数据：
   python analyze_batch_results.py --result-dir xxx --output-format json --output-file summary.json
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime
from pathlib import Path
from collections import defaultdict, Counter


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='AutoChip Batch Test Results Analyzer')
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--result-dir', '-r', type=str, help='单个实验结果目录路径')
    group.add_argument('--batch-dir', '-b', type=str, help='批量测试结果根目录（用于对比多个实验）')
    
    parser.add_argument('--compare', '-c', action='store_true', help='对比模式：分析batch-dir下的所有实验')
    parser.add_argument('--output-format', '-f', choices=['console', 'markdown', 'json'], default='console')
    parser.add_argument('--output-file', '-o', type=str, help='输出文件路径（默认为控制台输出）')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细题目信息')
    
    return parser.parse_args()


def load_result_json(result_dir):
    """加载实验结果JSON文件"""
    json_files = list(Path(result_dir).glob('results_*.json'))
    if not json_files:
        print(f"Warning: No result JSON file found in {result_dir}")
        return None
    
    with open(json_files[0], 'r') as f:
        return json.load(f)


def scan_experiment_directory(result_dir):
    """
    直接扫描实验目录，从日志文件中提取所有问题的结果
    不依赖JSON结果文件，避免check_if_completed的bug
    
    Returns:
        dict: 包含配置信息和详细结果的字典
    """
    result_dir = Path(result_dir)
    
    # 查找所有问题目录
    prob_dirs = sorted([d for d in result_dir.iterdir() if d.is_dir() and d.name.startswith('Prob')])
    
    if not prob_dirs:
        print(f"❌ Error: No problem directories found in {result_dir}")
        return None
    
    details = []
    total_iterations = 0
    total_time = 0
    
    print(f"🔍 Scanning {len(prob_dirs)} problem directories...")
    
    for prob_dir in prob_dirs:
        prob_id = prob_dir.name
        log_path = prob_dir / 'log.txt'
        
        if not log_path.exists():
            print(f"  ⚠️  Skipping {prob_id}: log.txt not found")
            continue
        
        # 解析日志文件
        log_info = parse_log_file_enhanced(str(log_path))
        
        if not log_info:
            print(f"  ⚠️  Skipping {prob_id}: failed to parse log")
            continue
        
        # 构建详细结果
        detail = {
            'problem': prob_id,
            'rank': log_info.get('final_rank', -1.0),
            'iterations_used': log_info.get('iterations', 0),
            'status': get_status_from_rank(log_info.get('final_rank', -1.0)),
            'model_info': log_info.get('models_used', []),
            'compilation_errors': log_info.get('compilation_errors', []),
            'simulation_errors': log_info.get('simulation_errors', []),
            'generation_time': log_info.get('generation_time', 0)
        }
        
        details.append(detail)
        total_iterations += log_info.get('iterations', 0)
        total_time += log_info.get('generation_time', 0)
    
    # 尝试从第一个配置文件推断实验配置
    config = infer_experiment_config(result_dir, prob_dirs)
    
    # 构建结果数据结构（与原有JSON格式兼容）
    result_data = {
        'config': config,
        'statistics': {
            'total': len(details),
            'passed': len([d for d in details if d['rank'] == 1.0]),
            'failed': len([d for d in details if 0 <= d['rank'] < 1.0]),
            'errors': len([d for d in details if d['rank'] < 0]),
            'skipped': 0,
            'pass_rate': (len([d for d in details if d['rank'] == 1.0]) / len(details) * 100) if details else 0,
            'elapsed_seconds': total_time,
            'avg_iterations': total_iterations / len(details) if details else 0
        },
        'details': details,
        'timestamp': datetime.now().isoformat(),
        'scan_method': 'direct_log_parsing'  # 标记数据来源
    }
    
    print(f"✅ Successfully scanned {len(details)} problems\n")
    return result_data


def parse_log_file_enhanced(log_path):
    """
    增强版日志解析器，提取更完整的信息
    
    Returns:
        dict: 包含rank、迭代次数、模型信息、耗时等
    """
    if not os.path.exists(log_path):
        return None
    
    info = {
        'iterations': 0,
        'final_rank': None,
        'models_used': [],
        'compilation_errors': [],
        'simulation_errors': [],
        'warnings': [],
        'generation_time': 0
    }
    
    try:
        with open(log_path, 'r') as f:
            content = f.read()
            lines = content.split('\n')
            
            # 提取迭代次数和每次使用的模型
            current_iter = -1
            models_in_iter = {}
            
            for line in lines:
                # 匹配 "Iteration: X"
                iter_match = re.search(r'Iteration:\s*(\d+)', line)
                if iter_match:
                    current_iter = int(iter_match.group(1))
                
                # 匹配 "Model type: XXX" 或 "Model: XXX"
                if current_iter >= 0:
                    model_match = re.search(r'Model(?:\s+type)?:\s*(.+)', line)
                    if model_match:
                        model_name = model_match.group(1).strip()
                        if current_iter not in models_in_iter:
                            models_in_iter[current_iter] = model_name
            
            info['iterations'] = len(models_in_iter)
            info['models_used'] = list(models_in_iter.values())
            
            # 提取最终Rank（支持多种格式）
            rank_patterns = [
                r'Rank of best response:\s*([-\d.]+)',
                r'Best.*Rank:\s*([-\d.]+)',
                r'Final Rank:\s*([-\d.]+)'
            ]
            
            for pattern in rank_patterns:
                rank_match = re.search(pattern, content)
                if rank_match:
                    info['final_rank'] = float(rank_match.group(1))
                    break
            
            # 如果没有找到Rank，检查是否有成功的迭代
            if info['final_rank'] is None:
                if re.search(r'Best ranked response at iteration', content):
                    # 找到了最佳响应，但Rank值缺失，可能是解析问题
                    info['final_rank'] = -1.0  # 标记为需要手动检查
            
            # 提取生成时间
            time_match = re.search(r'Time to Generate:\s*([\d.]+)', content)
            if time_match:
                info['generation_time'] = float(time_match.group(1))
            
            # 提取编译错误（简化版）
            error_matches = re.findall(r'(?:iverilog|vvp).*?(?:error|Error)[:\s].*?(?=\n|$)', content)
            info['compilation_errors'] = [e.strip() for e in error_matches[:3]]
            
            # 提取仿真断言失败
            assertion_matches = re.findall(r'Assertion\s+(?:failed|error).*?(?=\n|$)', content, re.IGNORECASE)
            info['simulation_errors'] = [e.strip() for e in assertion_matches[:3]]
    
    except Exception as e:
        print(f"Warning: Failed to parse log file {log_path}: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    return info


def get_status_from_rank(rank):
    """根据Rank值确定状态"""
    if rank is None or rank < 0:
        return "FAIL"
    elif rank == 1.0:
        return "PASS"
    else:
        return "PARTIAL"


def infer_experiment_config(result_dir, prob_dirs):
    """
    从目录结构和配置文件推断实验配置
    """
    config = {
        'iterations': 'unknown',
        'candidates': 'unknown',
        'mixed_models': False,
        'experiment_name': result_dir.name
    }
    
    # 尝试从第一个问题的子目录推断迭代次数和候选数
    if prob_dirs:
        first_prob = prob_dirs[0]
        iter_dirs = [d for d in first_prob.iterdir() if d.is_dir() and d.name.startswith('iter')]
        if iter_dirs:
            # 迭代次数 = iter目录数量
            config['iterations'] = len(iter_dirs) - 1  # iter0-iterN，所以是N
            
            # 从第一个iter目录推断候选数
            first_iter = sorted(iter_dirs)[0]
            response_dirs = [d for d in first_iter.iterdir() if d.is_dir() and d.name.startswith('response')]
            if response_dirs:
                config['candidates'] = len(response_dirs)
    
    # 检查是否有混合模型配置
    config_files = list(result_dir.glob('configs/config_*.json'))
    if config_files:
        try:
            with open(config_files[0], 'r') as f:
                prob_config = json.load(f)
                if prob_config.get('general', {}).get('mixed-models', False):
                    config['mixed_models'] = True
        except:
            pass
    
    return config


def parse_log_file(log_path):
    """解析单个问题的日志文件，提取关键信息"""
    if not os.path.exists(log_path):
        return {}
    
    info = {
        'iterations': 0,
        'final_rank': None,
        'compilation_errors': [],
        'simulation_errors': [],
        'warnings': []
    }
    
    try:
        with open(log_path, 'r') as f:
            content = f.read()
            
            # 提取迭代次数
            iter_matches = re.findall(r'Iteration (\d+)', content)
            if iter_matches:
                info['iterations'] = int(max(iter_matches)) + 1
            
            # 提取最终Rank
            rank_match = re.search(r'Rank of best response:\s*([-\d.]+)', content)
            if rank_match:
                info['final_rank'] = float(rank_match.group(1))
            
            # 提取编译错误
            comp_errors = re.findall(r'Error:.*?(?=\n\n|\nRank|$)', content, re.DOTALL)
            info['compilation_errors'] = [e.strip() for e in comp_errors[:3]]  # 最多保留3个
            
            # 提取仿真错误
            sim_errors = re.findall(r'(?:Simulation|Assertion).*?Error:.*?(?=\n\n|\nRank|$)', content, re.DOTALL)
            info['simulation_errors'] = [e.strip() for e in sim_errors[:3]]
            
            # 提取警告
            warnings = re.findall(r'Warning:.*?(?=\n)', content)
            info['warnings'] = [w.strip() for w in warnings[:5]]
    
    except Exception as e:
        print(f"Warning: Failed to parse log file {log_path}: {e}")
    
    return info


def analyze_single_experiment(result_dir, verbose=False):
    """分析单个实验的结果"""
    print(f"\n{'='*80}")
    print(f"Analyzing experiment: {os.path.basename(result_dir)}")
    print(f"{'='*80}\n")
    
    # 优先使用直接扫描方法，不依赖可能有bug的JSON文件
    result_data = scan_experiment_directory(result_dir)
    
    # 如果扫描失败，回退到加载JSON文件
    if not result_data:
        print("⚠️  Falling back to JSON file parsing...")
        result_data = load_result_json(result_dir)
        if not result_data:
            print("❌ Error: Cannot load experiment data")
            return None
    
    # 基本统计
    stats = result_data.get('statistics', {})
    config = result_data.get('config', {})
    details = result_data.get('details', [])
    
    print("📊 Experiment Configuration:")
    iterations = config.get('iterations', 'N/A')
    if isinstance(iterations, int):
        print(f"  - Iterations: {iterations} (executed {iterations + 1} times)")
    else:
        print(f"  - Iterations: {iterations}")
    print(f"  - Candidates per iteration: {config.get('candidates', 'N/A')}")
    print(f"  - Mixed Models: {'Yes' if config.get('mixed_models') else 'No'}")
    print(f"  - Timestamp: {result_data.get('timestamp', 'N/A')}")
    print()
    
    print("📈 Key Metrics:")
    print(f"  - Total Problems: {stats.get('total', 0)}")
    print(f"  - Passed (Rank=1.0): {stats.get('passed', 0)}")
    print(f"  - Partially Passed (0<Rank<1): {stats.get('failed', 0)}")
    print(f"  - Failed/Errors (Rank<0): {stats.get('errors', 0)}")
    print(f"  - Skipped: {stats.get('skipped', 0)}")
    print(f"  - Pass Rate: {stats.get('pass_rate', 0):.2f}%")
    print(f"  - Elapsed Time: {stats.get('elapsed_seconds', 0):.1f}s ({stats.get('elapsed_seconds', 0)/60:.1f}min)")
    print()
    
    # 计算平均Rank
    ranks = [d['rank'] for d in details]
    avg_rank = sum(ranks) / len(ranks) if ranks else 0
    print(f"  - Average Rank: {avg_rank:.4f}")
    print()
    
    # 分类统计
    perfect_solutions = [d for d in details if d['rank'] == 1.0]
    partial_solutions = [d for d in details if 0 <= d['rank'] < 1.0]
    failed_solutions = [d for d in details if d['rank'] < 0]
    
    print("🎯 Solution Quality Distribution:")
    print(f"  - Perfect Solutions (Rank=1.0): {len(perfect_solutions)} ({len(perfect_solutions)/len(details)*100:.1f}%)")
    print(f"  - Partial Solutions (0≤Rank<1): {len(partial_solutions)} ({len(partial_solutions)/len(details)*100:.1f}%)")
    print(f"  - Failed Solutions (Rank<0): {len(failed_solutions)} ({len(failed_solutions)/len(details)*100:.1f}%)")
    print()
    
    # 详细题目信息
    if verbose:
        print("📋 Detailed Problem Results:")
        print("-" * 80)
        
        # 按Rank排序
        sorted_details = sorted(details, key=lambda x: x['rank'], reverse=True)
        
        for item in sorted_details:
            prob_id = item['problem']
            rank = item['rank']
            
            # 确定状态
            if rank == 1.0:
                status = "✅ PASS"
            elif rank >= 0:
                status = "⚠️  PARTIAL"
            else:
                status = "❌ FAIL"
            
            # 解析日志获取更多信息
            log_path = os.path.join(result_dir, prob_id, 'log.txt')
            log_info = parse_log_file(log_path)
            
            print(f"\n{prob_id}:")
            print(f"  Status: {status}")
            print(f"  Rank: {rank:.4f}")
            if log_info.get('iterations'):
                print(f"  Iterations Used: {log_info['iterations']}")
            
            if log_info.get('compilation_errors'):
                print(f"  Compilation Errors: {len(log_info['compilation_errors'])}")
                for err in log_info['compilation_errors'][:1]:
                    print(f"    - {err[:100]}...")
            
            if log_info.get('simulation_errors'):
                print(f"  Simulation Errors: {len(log_info['simulation_errors'])}")
        
        print("\n" + "-" * 80)
    
    # 失败原因分析
    if failed_solutions:
        print("\n❌ Failed Problems Analysis:")
        print("-" * 80)
        
        fail_reasons = defaultdict(int)
        for item in failed_solutions:
            prob_id = item['problem']
            rank = item['rank']
            
            log_path = os.path.join(result_dir, prob_id, 'log.txt')
            log_info = parse_log_file(log_path)
            
            if rank == -2.0:
                fail_reasons['No Code Generated'] += 1
            elif rank == -1.0:
                if log_info.get('compilation_errors'):
                    fail_reasons['Compilation Error'] += 1
                else:
                    fail_reasons['Unknown Compilation Issue'] += 1
            elif rank == -0.5:
                fail_reasons['Warnings Only'] += 1
            else:
                fail_reasons['Other Issues'] += 1
        
        for reason, count in sorted(fail_reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {reason}: {count} problems")
        
        print()
        print("Failed Problem IDs:")
        for item in failed_solutions:
            print(f"  - {item['problem']} (Rank: {item['rank']})")
    
    # 部分通过的题目
    if partial_solutions and verbose:
        print("\n⚠️  Partially Passed Problems:")
        print("-" * 80)
        sorted_partial = sorted(partial_solutions, key=lambda x: x['rank'], reverse=True)
        for item in sorted_partial:
            print(f"  - {item['problem']}: Rank={item['rank']:.4f}")
    
    # 生成Markdown报告
    if args.output_format == 'markdown':
        md_content = generate_markdown_report(result_data, details, stats, config, avg_rank)
        return md_content
    
    # 生成JSON摘要
    if args.output_format == 'json':
        summary = {
            'experiment_dir': os.path.basename(result_dir),
            'config': config,
            'statistics': stats,
            'average_rank': round(avg_rank, 4),
            'perfect_solutions': len(perfect_solutions),
            'partial_solutions': len(partial_solutions),
            'failed_solutions': len(failed_solutions),
            'pass_rate': stats.get('pass_rate', 0),
            'elapsed_seconds': stats.get('elapsed_seconds', 0),
        }
        return summary
    
    return None


def generate_markdown_report(result_data, details, stats, config, avg_rank):
    """生成Markdown格式的报告"""
    timestamp = result_data.get('timestamp', 'N/A')
    experiment_name = os.path.basename(result_data.get('experiment_dir', 'unknown'))
    
    md = []
    md.append(f"# AutoChip Batch Test Report\n")
    md.append(f"**Experiment**: {experiment_name}  \n")
    md.append(f"**Timestamp**: {timestamp}  \n")
    md.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    md.append("## Configuration\n")
    iterations = config.get('iterations', 'N/A')
    if isinstance(iterations, int):
        md.append(f"- **Iterations**: {iterations} (executed {iterations + 1} times)")
    else:
        md.append(f"- **Iterations**: {iterations}")
    md.append(f"- **Candidates per Iteration**: {config.get('candidates', 'N/A')}")
    md.append(f"- **Mixed Models**: {'Yes' if config.get('mixed_models') else 'No'}\n")
    
    md.append("## Key Metrics\n")
    md.append("| Metric | Value |")
    md.append("|--------|-------|")
    md.append(f"| Total Problems | {stats.get('total', 0)} |")
    md.append(f"| Passed (Rank=1.0) | {stats.get('passed', 0)} |")
    md.append(f"| Partially Passed | {stats.get('failed', 0)} |")
    md.append(f"| Failed/Errors | {stats.get('errors', 0)} |")
    md.append(f"| Skipped | {stats.get('skipped', 0)} |")
    md.append(f"| **Pass Rate** | **{stats.get('pass_rate', 0):.2f}%** |")
    md.append(f"| Average Rank | {avg_rank:.4f} |")
    md.append(f"| Elapsed Time | {stats.get('elapsed_seconds', 0):.1f}s ({stats.get('elapsed_seconds', 0)/60:.1f}min)\n")
    
    # 完美解决方案列表
    perfect = [d for d in details if d['rank'] == 1.0]
    if perfect:
        md.append("## ✅ Perfect Solutions (Rank=1.0)\n")
        for item in perfect:
            md.append(f"- {item['problem']}")
        md.append("")
    
    # 部分解决方案
    partial = [d for d in details if 0 <= d['rank'] < 1.0]
    if partial:
        md.append("## ⚠️ Partially Passed Solutions\n")
        md.append("| Problem | Rank |")
        md.append("|---------|------|")
        sorted_partial = sorted(partial, key=lambda x: x['rank'], reverse=True)
        for item in sorted_partial:
            md.append(f"| {item['problem']} | {item['rank']:.4f} |")
        md.append("")
    
    # 失败方案
    failed = [d for d in details if d['rank'] < 0]
    if failed:
        md.append("## ❌ Failed Solutions\n")
        md.append("| Problem | Rank |")
        md.append("|---------|------|")
        for item in failed:
            md.append(f"| {item['problem']} | {item['rank']} |")
        md.append("")
    
    return '\n'.join(md)


def compare_experiments(batch_dir):
    """对比多个实验的结果"""
    print(f"\n{'='*80}")
    print(f"Comparing Experiments in: {batch_dir}")
    print(f"{'='*80}\n")
    
    # 查找所有包含results_*.json的目录
    experiments = []
    for item in Path(batch_dir).iterdir():
        if item.is_dir():
            json_files = list(item.glob('results_*.json'))
            if json_files:
                experiments.append(str(item))
    
    if not experiments:
        print("No experiment results found!")
        return
    
    print(f"Found {len(experiments)} experiments:\n")
    for exp in experiments:
        print(f"  - {os.path.basename(exp)}")
    print()
    
    # 分析每个实验
    summaries = []
    for exp_dir in experiments:
        result_data = load_result_json(exp_dir)
        if result_data:
            stats = result_data.get('statistics', {})
            config = result_data.get('config', {})
            details = result_data.get('details', [])
            ranks = [d['rank'] for d in details]
            avg_rank = sum(ranks) / len(ranks) if ranks else 0
            
            summaries.append({
                'name': os.path.basename(exp_dir),
                'config': config,
                'stats': stats,
                'avg_rank': avg_rank,
                'total': stats.get('total', 0),
                'passed': stats.get('passed', 0),
                'pass_rate': stats.get('pass_rate', 0),
                'elapsed': stats.get('elapsed_seconds', 0),
            })
    
    # 打印对比表格
    print("📊 Comparison Summary:\n")
    print(f"{'Experiment':<50} {'Pass Rate':>10} {'Avg Rank':>10} {'Passed':>8} {'Total':>8} {'Time(min)':>10}")
    print("-" * 100)
    
    for s in sorted(summaries, key=lambda x: x['pass_rate'], reverse=True):
        time_min = s['elapsed'] / 60
        print(f"{s['name']:<50} {s['pass_rate']:>9.2f}% {s['avg_rank']:>10.4f} {s['passed']:>8} {s['total']:>8} {time_min:>10.1f}")
    
    print()
    
    # 生成Markdown对比报告
    if args.output_format == 'markdown':
        md = []
        md.append("# AutoChip Experiments Comparison\n")
        md.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        md.append("## Summary\n")
        md.append("| Experiment | Pass Rate | Avg Rank | Passed | Total | Time(min) |")
        md.append("|------------|-----------|----------|--------|-------|-----------|")
        for s in sorted(summaries, key=lambda x: x['pass_rate'], reverse=True):
            time_min = s['elapsed'] / 60
            md.append(f"| {s['name']} | {s['pass_rate']:.2f}% | {s['avg_rank']:.4f} | {s['passed']} | {s['total']} | {time_min:.1f} |")
        md.append("")
        return '\n'.join(md)
    
    if args.output_format == 'json':
        return {'experiments': summaries}
    
    return None


def main():
    global args
    args = parse_args()
    
    output_content = None
    
    if args.result_dir:
        # 分析单个实验
        if not os.path.exists(args.result_dir):
            print(f"Error: Directory not found: {args.result_dir}")
            sys.exit(1)
        
        output_content = analyze_single_experiment(args.result_dir, args.verbose)
    
    elif args.batch_dir:
        # 对比多个实验
        if not os.path.exists(args.batch_dir):
            print(f"Error: Directory not found: {args.batch_dir}")
            sys.exit(1)
        
        output_content = compare_experiments(args.batch_dir)
    
    # 输出结果
    if output_content:
        if args.output_file:
            with open(args.output_file, 'w') as f:
                if isinstance(output_content, str):
                    f.write(output_content)
                else:
                    json.dump(output_content, f, indent=2)
            print(f"\nReport saved to: {args.output_file}")
        else:
            if isinstance(output_content, str):
                print(output_content)
            else:
                print(json.dumps(output_content, indent=2))


if __name__ == '__main__':
    main()

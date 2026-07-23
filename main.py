"""
Rime 远程词库同步与 AI 智能调优服务主程序
支持 --mode incremental (白天增量), --mode deep (晚间深度), --mode merge_only
"""

import os
import sys
import json
import argparse
import logging
from typing import Dict, List, Tuple
from rime_parser import RimeParser, UserDbEntry
from rime_merger import RimeMerger
from ai_optimizer import AIOptimizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def load_config(config_path: str) -> dict:
    if not os.path.exists(config_path):
        logging.error(f"配置文件不存在: {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_sync_and_optimize(config_path: str, mode: str):
    config = load_config(config_path)
    sync_dir = config.get("sync_dir", "/var/webdav/rime/sync")
    dist_dir = config.get("dist_dir", "/var/webdav/rime/sync/dist")
    backup_dir = config.get("backup_dir", "/var/webdav/rime/backups")
    snapshot_dir = os.path.join(backup_dir, "snapshots")
    dict_names = config.get("dict_names", ["rime_ice", "luna_pinyin"])
    opencode_bin = config.get("opencode_bin", "opencode")
    rules = config.get("rules", {})

    merger = RimeMerger(sync_dir=sync_dir, backup_dir=backup_dir, weight_decay=rules.get("weight_decay", 0.9))
    optimizer = AIOptimizer(opencode_bin=opencode_bin, max_batch_size=rules.get("max_ai_batch_size", 30))

    os.makedirs(dist_dir, exist_ok=True)
    os.makedirs(snapshot_dir, exist_ok=True)

    for dict_name in dict_names:
        logging.info(f"=== 开始处理字典 [{dict_name}] | 模式: {mode} ===")

        # 1. 多端词库合并
        headers, merged_entries = merger.merge_all(dict_name)
        if not merged_entries:
            logging.info(f"字典 [{dict_name}] 未扫描到有效条目，跳过。")
            continue

        snapshot_file = os.path.join(snapshot_dir, f"{dict_name}_last_snapshot.userdb.txt")

        # 2. 根据模式执行 AI 调优
        max_daily_ai_limit = rules.get("max_daily_ai_limit", 50)
        skip_high_freq = rules.get("skip_high_freq_threshold", 50)

        if mode == "incremental":
            # 漏斗筛选增量条目
            incremental_entries = merger.get_incremental_entries(
                merged_entries,
                snapshot_file,
                max_limit=max_daily_ai_limit,
                skip_high_freq=skip_high_freq
            )
            logging.info(f"漏斗筛选后获取 {len(incremental_entries)} 条疑难/新增词汇交给 AI 分析...")

            if incremental_entries:
                optimized_inc = optimizer.optimize_incremental(incremental_entries)
                for opt_entry in optimized_inc:
                    key = (opt_entry.word, opt_entry.code)
                    merged_entries[key] = opt_entry

        elif mode == "deep":
            # 漏斗筛选深度疑难候选词
            candidates = merger.get_deep_candidates(
                merged_entries,
                max_limit=max_daily_ai_limit,
                skip_high_freq=skip_high_freq
            )
            logging.info(f"漏斗筛选后获取 {len(candidates)} 条疑难候选词交给 AI 深度分析...")

            if candidates:
                optimized_deep = optimizer.optimize_deep(candidates)
                for opt_entry in optimized_deep:
                    key = (opt_entry.word, opt_entry.code)
                    merged_entries[key] = opt_entry

        elif mode == "merge_only":
            logging.info("仅执行合并，不调用 AI 调优。")

        # 3. 分发与导出最终词库
        dist_userdb_file = os.path.join(dist_dir, f"{dict_name}.userdb.txt")
        dist_custom_phrase_file = os.path.join(dist_dir, "custom_phrase.txt")

        logging.info(f"导出分发词库: {dist_userdb_file}")
        RimeParser.dump_userdb(dist_userdb_file, headers, merged_entries)

        logging.info(f"导出 custom_phrase 词库: {dist_custom_phrase_file}")
        RimeParser.dump_custom_phrase(dist_custom_phrase_file, merged_entries)

        # 4. 保存当前快照
        merger.save_snapshot(snapshot_file, merged_entries)
        logging.info(f"字典 [{dict_name}] 处理完成！\n")


def main():
    parser = argparse.ArgumentParser(description="Rime 输入法远程词库同步与 AI 调优服务")
    parser.add_argument(
        "--config",
        default="config.json",
        help="配置文件路径 (默认: config.json)"
    )
    parser.add_argument(
        "--mode",
        choices=["incremental", "deep", "merge_only"],
        default="incremental",
        help="运行模式: incremental (白天增量), deep (晚间深度), merge_only (仅合并)"
    )

    args = parser.parse_args()
    run_sync_and_optimize(args.config, args.mode)

if __name__ == "__main__":
    main()

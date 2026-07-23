"""
多端 Rime 词库合并与增量提取引擎
"""

import os
import glob
import math
import json
from typing import Dict, List, Tuple, Set, Optional
from rime_parser import RimeParser, UserDbEntry

class RimeMerger:
    def __init__(self, sync_dir: str, backup_dir: str, weight_decay: float = 0.9):
        self.sync_dir = sync_dir
        self.backup_dir = backup_dir
        self.weight_decay = weight_decay

    def find_client_dirs(self) -> List[str]:
        """寻找 sync_dir 下的所有终端子目录（排除 dist 与 backup 目录）"""
        if not os.path.exists(self.sync_dir):
            return []
        
        client_dirs = []
        for entry in os.listdir(self.sync_dir):
            full_path = os.path.join(self.sync_dir, entry)
            if os.path.isdir(full_path) and entry not in ["dist", "backups", "snapshots"]:
                client_dirs.append(full_path)
        return client_dirs

    def merge_all(self, dict_name: str) -> Tuple[List[str], Dict[Tuple[str, str], UserDbEntry]]:
        """
        合并所有终端的对应字典 (如 rime_ice.userdb.txt 或 custom_phrase.txt)
        """
        client_dirs = self.find_client_dirs()
        merged_entries: Dict[Tuple[str, str], UserDbEntry] = {}
        merged_headers: List[str] = [
            "# Rime user dictionary database dump",
            f"# db_name: {dict_name}",
            "# db_type: userdb (merged by rime-aisync)"
        ]

        # 用字典记录每个词在多少个客户端出现过以及累加权重
        word_client_counts: Dict[Tuple[str, str], int] = {}

        for c_dir in client_dirs:
            target_file = os.path.join(c_dir, f"{dict_name}.userdb.txt")
            if not os.path.exists(target_file):
                # 尝试寻找 *.userdb.txt
                matches = glob.glob(os.path.join(c_dir, "*.userdb.txt"))
                if matches:
                    target_file = matches[0]
                else:
                    continue

            _, entries = RimeParser.parse_file(target_file)

            for key, entry in entries.items():
                word_client_counts[key] = word_client_counts.get(key, 0) + 1
                if key not in merged_entries:
                    merged_entries[key] = UserDbEntry(
                        word=entry.word,
                        code=entry.code,
                        weight=entry.weight,
                        commit_count=entry.commit_count,
                        last_commit_time=entry.last_commit_time
                    )
                else:
                    existing = merged_entries[key]
                    # 多端词频累加 + 对数平滑
                    new_commit = existing.commit_count + entry.commit_count
                    new_weight = max(existing.weight, entry.weight) + math.log1p(entry.weight) * self.weight_decay
                    new_time = max(existing.last_commit_time, entry.last_commit_time)

                    existing.commit_count = new_commit
                    existing.weight = round(new_weight, 4)
                    existing.last_commit_time = new_time
                    existing.raw_meta = f"c={new_commit} d={existing.weight:.4f}"
                    if new_time > 0:
                        existing.raw_meta += f" t={new_time}"

        return merged_headers, merged_entries

    def get_incremental_entries(
        self,
        current_entries: Dict[Tuple[str, str], UserDbEntry],
        snapshot_filepath: str,
        max_limit: int = 50,
        skip_high_freq: int = 50
    ) -> List[UserDbEntry]:
        """
        对比当前合并的词库与上一次的快照，获取真正的增量/异常词条（白天模式）
        采用漏斗过滤：过滤单字、过滤超高频词
        """
        if not os.path.exists(snapshot_filepath):
            # 无快照，抽取最新且长度>=2、词频适中的候选词
            candidates = [
                e for e in current_entries.values()
                if len(e.word) >= 2 and e.commit_count <= skip_high_freq
            ]
            return candidates[:max_limit]

        _, prev_entries = RimeParser.parse_file(snapshot_filepath)
        incremental: List[UserDbEntry] = []

        for key, entry in current_entries.items():
            # 跳过单字
            if len(entry.word) < 2:
                continue

            # 跳过超高频稳定词
            if entry.commit_count > skip_high_freq:
                continue

            if key not in prev_entries:
                incremental.append(entry)
            else:
                prev_entry = prev_entries[key]
                # 提交次数有变化但词频不高，疑难变更
                if entry.commit_count > prev_entry.commit_count:
                    incremental.append(entry)

            if len(incremental) >= max_limit:
                break

        return incremental

    def get_deep_candidates(
        self,
        current_entries: Dict[Tuple[str, str], UserDbEntry],
        max_limit: int = 50,
        skip_high_freq: int = 50
    ) -> List[UserDbEntry]:
        """
        抽取需要晚间深度调优的疑难候选词条
        规则：词长>=2，排除超高频已稳定词，优先抽取最近有提交或偶发低频多字词
        """
        candidates: List[UserDbEntry] = []
        for entry in current_entries.values():
            # 过滤单字
            if len(entry.word) < 2:
                continue

            # 过滤超高频稳定词（高频常用词没必要浪费 AI token）
            if entry.commit_count > skip_high_freq:
                continue

            candidates.append(entry)

        # 按最后提交时间倒序，若无时间按词长倒序（长词组更容易包含错别字）
        candidates.sort(key=lambda x: (-x.last_commit_time, len(x.word), x.commit_count))
        return candidates[:max_limit]

    def save_snapshot(self, snapshot_filepath: str, entries: Dict[Tuple[str, str], UserDbEntry]) -> None:
        """保存合并结果快照"""
        os.makedirs(os.path.dirname(os.path.abspath(snapshot_filepath)), exist_ok=True)
        RimeParser.dump_userdb(snapshot_filepath, ["# Rime snapshot file"], entries)

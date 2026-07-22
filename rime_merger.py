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
        snapshot_filepath: str
    ) -> List[UserDbEntry]:
        """
        对比当前合并的词库与上一次的快照，获取新增与显著变动的增量条目（用于白天模式）
        """
        if not os.path.exists(snapshot_filepath):
            # 无快照，默认返回所有新增词或前 N 条新词
            return list(current_entries.values())

        _, prev_entries = RimeParser.parse_file(snapshot_filepath)
        incremental: List[UserDbEntry] = []

        for key, entry in current_entries.items():
            if key not in prev_entries:
                incremental.append(entry)
            else:
                prev_entry = prev_entries[key]
                # 若提交数显著增加（例如增加 2 次以上），也纳入增量调优
                if entry.commit_count - prev_entry.commit_count >= 2:
                    incremental.append(entry)

        return incremental

    def get_deep_candidates(
        self,
        current_entries: Dict[Tuple[str, str], UserDbEntry],
        max_count: int = 100
    ) -> List[UserDbEntry]:
        """
        抽取需要晚间深度调优的候选词条（优先处理低词频长词、可能存在的错别字或冲突词）
        """
        candidates: List[UserDbEntry] = []
        for entry in current_entries.values():
            # 候选条件：词长 >= 2，词频较高或极其可疑的低频词组
            if len(entry.word) >= 2:
                candidates.append(entry)

        # 优先按时间戳倒序或低频疑难词排序
        candidates.sort(key=lambda x: (x.last_commit_time == 0, -x.last_commit_time, x.commit_count))
        return candidates[:max_count]

    def save_snapshot(self, snapshot_filepath: str, entries: Dict[Tuple[str, str], UserDbEntry]) -> None:
        """保存合并结果快照"""
        os.makedirs(os.path.dirname(os.path.abspath(snapshot_filepath)), exist_ok=True)
        RimeParser.dump_userdb(snapshot_filepath, ["# Rime snapshot file"], entries)

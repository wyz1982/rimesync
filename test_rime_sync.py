"""
Rime 远程词库同步与 AI 调优全流程单元测试脚本
"""

import os
import shutil
import unittest
import tempfile
import json
from rime_parser import RimeParser, UserDbEntry
from rime_merger import RimeMerger
from ai_optimizer import AIOptimizer
from main import run_sync_and_optimize

class TestRimeSync(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.sync_dir = os.path.join(self.test_dir, "sync")
        self.dist_dir = os.path.join(self.sync_dir, "dist")
        self.backup_dir = os.path.join(self.test_dir, "backups")
        
        # 建立客户端 1 (Win-PC) 与 客户端 2 (Mac-Laptop) 模拟数据
        self.client_win = os.path.join(self.sync_dir, "win-pc")
        self.client_mac = os.path.join(self.sync_dir, "mac-laptop")

        os.makedirs(self.client_win, exist_ok=True)
        os.makedirs(self.client_mac, exist_ok=True)

        # 模拟 Win 端词条
        win_entries = {
            ("人工智能", "ren gong zhi neng"): UserDbEntry("人工智能", "ren gong zhi neng", weight=10.0, commit_count=10),
            ("再接再励", "zai jie zai li"): UserDbEntry("再接再励", "zai jie zai li", weight=2.0, commit_count=2), # 包含错别字
        }
        RimeParser.dump_userdb(os.path.join(self.client_win, "rime_ice.userdb.txt"), [], win_entries)

        # 模拟 Mac 端词条
        mac_entries = {
            ("人工智能", "ren gong zhi neng"): UserDbEntry("人工智能", "ren gong zhi neng", weight=5.0, commit_count=5),
            ("开源项目", "kai yuan xiang mu"): UserDbEntry("开源项目", "kai yuan xiang mu", weight=3.0, commit_count=3),
        }
        RimeParser.dump_userdb(os.path.join(self.client_mac, "rime_ice.userdb.txt"), [], mac_entries)

        # 写入配置文件
        self.config_path = os.path.join(self.test_dir, "config.json")
        config_data = {
            "sync_dir": self.sync_dir,
            "dist_dir": self.dist_dir,
            "backup_dir": self.backup_dir,
            "dict_names": ["rime_ice"],
            "opencode_bin": "opencode_non_exist", # 测试无 OpenCode CLI 时的安全降级
            "rules": {
                "min_freq_threshold": 1,
                "weight_decay": 0.9,
                "max_ai_batch_size": 30
            }
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_merger(self):
        merger = RimeMerger(self.sync_dir, self.backup_dir)
        headers, merged = merger.merge_all("rime_ice")

        # 验证词汇融合
        self.assertIn(("人工智能", "ren gong zhi neng"), merged)
        self.assertIn(("开源项目", "kai yuan xiang mu"), merged)
        self.assertIn(("再接再励", "zai jie zai li"), merged)

        # 验证词频加权 (10 + 5 对数累加)
        ai_entry = merged[("人工智能", "ren gong zhi neng")]
        self.assertEqual(ai_entry.commit_count, 15)
        self.assertGreater(ai_entry.weight, 10.0)

    def test_full_pipeline_merge_only(self):
        run_sync_and_optimize(self.config_path, mode="merge_only")

        dist_userdb = os.path.join(self.dist_dir, "rime_ice.userdb.txt")
        dist_custom = os.path.join(self.dist_dir, "custom_phrase.txt")

        self.assertTrue(os.path.exists(dist_userdb))
        self.assertTrue(os.path.exists(dist_custom))

        _, entries = RimeParser.parse_file(dist_userdb)
        self.assertIn(("人工智能", "ren gong zhi neng"), entries)

    def test_fallback_safety(self):
        # 验证即使 OpenCode CLI 不可用，也绝对不会损坏词库
        run_sync_and_optimize(self.config_path, mode="incremental")
        dist_userdb = os.path.join(self.dist_dir, "rime_ice.userdb.txt")
        self.assertTrue(os.path.exists(dist_userdb))

if __name__ == "__main__":
    unittest.main()

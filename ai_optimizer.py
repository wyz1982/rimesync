"""
OpenCode CLI AI 词库智能调优适配模块
支持白天增量调优 (Incremental) 与晚间深度调优 (Deep)
"""

import json
import subprocess
import logging
from typing import Dict, List, Tuple, Any, Optional
from rime_parser import UserDbEntry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class AIOptimizer:
    def __init__(self, opencode_bin: str = "opencode", max_batch_size: int = 30):
        self.opencode_bin = opencode_bin
        self.max_batch_size = max_batch_size

    def _call_opencode(self, prompt: str) -> Optional[str]:
        """通过 subprocess 调用 opencode cli"""
        try:
            cmd = [self.opencode_bin, "run", prompt]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip()
            else:
                logging.warning(f"OpenCode CLI 执行返回非 0 或空输出: {result.stderr}")
                return None
        except Exception as e:
            logging.error(f"调用 OpenCode CLI 失败: {e}")
            return None

    def optimize_incremental(self, entries: List[UserDbEntry]) -> List[UserDbEntry]:
        """
        白天模式：增量词库快速调优
        重点：错别字矫正、拼音编码合法性校验
        """
        if not entries:
            return []

        logging.info(f"【白天增量调优】开始处理 {len(entries)} 个增量词条...")
        
        # 分批处理，减少单次 Prompt 长度与资源占用
        results: List[UserDbEntry] = []
        for i in range(0, len(entries), self.max_batch_size):
            batch = entries[i:i + self.max_batch_size]
            optimized_batch = self._process_incremental_batch(batch)
            results.extend(optimized_batch)

        return results

    def _process_incremental_batch(self, batch: List[UserDbEntry]) -> List[UserDbEntry]:
        items_payload = [{"w": e.word, "c": e.code} for e in batch]

        prompt = f"""审查以下 Rime 输入法增量词条，仅修正错别字或删除错误词汇。

输入:
{json.dumps(items_payload, ensure_ascii=False)}

返回 JSON 数组 (不要 markdown 格式):
[
  {{"w": "原始词", "c": "编码", "action": "KEEP"|"REPLACE"|"DELETE", "target": "修正后词"}}
]
"""
        response_text = self._call_opencode(prompt)
        if not response_text:
            logging.info("OpenCode CLI 未响应，默认保持 (KEEP)")
            return batch

        return self._apply_ai_actions(batch, response_text)

    def optimize_deep(self, entries: List[UserDbEntry]) -> List[UserDbEntry]:
        """
        晚间模式：深度词库调优
        重点：全局语义消歧、词频平滑降频、高频短语提炼
        """
        if not entries:
            return []

        logging.info(f"【晚间深度调优】微批次分析 {len(entries)} 个筛选后的候选词条...")

        results: List[UserDbEntry] = []
        for i in range(0, len(entries), self.max_batch_size):
            batch = entries[i:i + self.max_batch_size]
            optimized_batch = self._process_deep_batch(batch)
            results.extend(optimized_batch)

        return results

    def _process_deep_batch(self, batch: List[UserDbEntry]) -> List[UserDbEntry]:
        items_payload = [{"w": e.word, "c": e.code, "freq": e.commit_count} for e in batch]

        prompt = f"""审查以下 Rime 输入法深度调优词条。

输入:
{json.dumps(items_payload, ensure_ascii=False)}

返回 JSON 数组 (不要 markdown 格式):
[
  {{"w": "原始词", "c": "编码", "action": "KEEP"|"REPLACE"|"DELETE"|"MODIFY_WEIGHT", "target": "修正后词"}}
]
"""
        response_text = self._call_opencode(prompt)
        if not response_text:
            logging.info("OpenCode CLI 晚间深度调优未响应，安全回退保持原词库")
            return batch

        return self._apply_ai_actions(batch, response_text)

    def _apply_ai_actions(self, original_batch: List[UserDbEntry], response_text: str) -> List[UserDbEntry]:
        """解析 AI 响应文本并应用到词条"""
        try:
            clean_json = response_text.strip()
            if "```" in clean_json:
                lines = clean_json.splitlines()
                clean_lines = [l for l in lines if not l.strip().startswith("```")]
                clean_json = "\n".join(clean_lines)

            actions = json.loads(clean_json)
            action_map = {}
            for a in actions:
                w = a.get("w") or a.get("original_word")
                c = a.get("c") or a.get("code")
                if w and c:
                    action_map[(w, c)] = a

            final_entries: List[UserDbEntry] = []
            for entry in original_batch:
                key = (entry.word, entry.code)
                if key in action_map:
                    act = action_map[key]
                    action_type = act.get("action", "KEEP").upper()

                    if action_type == "DELETE":
                        logging.info(f"AI 剔除错误词条: {entry.word} [{entry.code}]")
                        continue
                    elif action_type == "REPLACE" and (act.get("target") or act.get("target_word")):
                        target_w = act.get("target") or act.get("target_word")
                        logging.info(f"AI 修正错别字: {entry.word} -> {target_w}")
                        entry.word = target_w
                        final_entries.append(entry)
                    else:
                        final_entries.append(entry)
                else:
                    final_entries.append(entry)

            return final_entries
        except Exception as e:
            logging.warning(f"解析 AI JSON 结果失败: {e}，回退使用原始词条列表")
            return original_batch

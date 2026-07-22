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
        items_payload = [{"word": e.word, "code": e.code, "freq": e.commit_count} for e in batch]

        prompt = f"""你是一个专业的汉语输入法词库专家。请对以下输入的 Rime 增量词条列表进行快速审查与矫正。

输入词条 JSON:
{json.dumps(items_payload, ensure_ascii=False)}

请检查并返回符合格式的 JSON 数组，数组每个对象包含：
- "original_word": 原始词条
- "code": 原始编码
- "action": 操作策略 (可选项: "KEEP" - 保持原样, "REPLACE" - 修正错别字, "DELETE" - 剔除无用错词/乱码)
- "target_word": 修正后的词条 (若 action 为 REPLACE)
- "reason": 简单说明

请直接输出标准 JSON 格式数据，不要带任何 markdown 或额外说明文字。
"""
        response_text = self._call_opencode(prompt)
        if not response_text:
            logging.info("OpenCode CLI 未响应或无法连接，回退为全量保持 (KEEP)")
            return batch

        return self._apply_ai_actions(batch, response_text)

    def optimize_deep(self, entries: List[UserDbEntry]) -> List[UserDbEntry]:
        """
        晚间模式：深度词库调优
        重点：全局语义消歧、词频平滑降频、高频短语提炼
        """
        if not entries:
            return []

        logging.info(f"【晚间深度调优】开始全局分析 {len(entries)} 个候选词条...")

        results: List[UserDbEntry] = []
        for i in range(0, len(entries), self.max_batch_size):
            batch = entries[i:i + self.max_batch_size]
            optimized_batch = self._process_deep_batch(batch)
            results.extend(optimized_batch)

        return results

    def _process_deep_batch(self, batch: List[UserDbEntry]) -> List[UserDbEntry]:
        items_payload = [{"word": e.word, "code": e.code, "freq": e.commit_count, "weight": e.weight} for e in batch]

        prompt = f"""你是一个专业的汉语输入法词库专家。请对以下 Rime 词库进行深度全局优化。

输入词条 JSON:
{json.dumps(items_payload, ensure_ascii=False)}

优化规则：
1. 找出输入错别字或歧义词条，予以修正或剔除。
2. 识别连续重复词或低效冗余词。
3. 对极低效过度膨胀的错误高频词给予合理降频建议。

请直接输出标准 JSON 数组，格式如下：
[
  {{
    "original_word": "词条",
    "code": "编码",
    "action": "KEEP" | "REPLACE" | "DELETE" | "MODIFY_WEIGHT",
    "target_word": "修正后词条",
    "new_weight": 修正后权重数值 (可选),
    "reason": "优化原因"
  }}
]
直接输出 JSON 结果。
"""
        response_text = self._call_opencode(prompt)
        if not response_text:
            logging.info("OpenCode CLI 晚间深度调优未响应，安全回退保持原词库")
            return batch

        return self._apply_ai_actions(batch, response_text)

    def _apply_ai_actions(self, original_batch: List[UserDbEntry], response_text: str) -> List[UserDbEntry]:
        """解析 AI 响应文本并应用到词条"""
        # 尝试提取 JSON 内容
        try:
            # 清理可能的 markdown 标记
            clean_json = response_text
            if "```" in clean_json:
                lines = clean_json.splitlines()
                clean_lines = [l for l in lines if not l.strip().startswith("```")]
                clean_json = "\n".join(clean_lines)

            actions = json.loads(clean_json)
            action_map = { (a["original_word"], a["code"]): a for a in actions if "original_word" in a and "code" in a }

            final_entries: List[UserDbEntry] = []
            for entry in original_batch:
                key = (entry.word, entry.code)
                if key in action_map:
                    act = action_map[key]
                    action_type = act.get("action", "KEEP").upper()

                    if action_type == "DELETE":
                        logging.info(f"AI 剔除词条: {entry.word} [{entry.code}] - 原因: {act.get('reason')}")
                        continue
                    elif action_type == "REPLACE" and act.get("target_word"):
                        target_w = act["target_word"]
                        logging.info(f"AI 修正错字: {entry.word} -> {target_w} - 原因: {act.get('reason')}")
                        entry.word = target_w
                        final_entries.append(entry)
                    elif action_type == "MODIFY_WEIGHT" and "new_weight" in act:
                        try:
                            entry.weight = float(act["new_weight"])
                            entry.raw_meta = f"c={entry.commit_count} d={entry.weight:.4f}"
                        except ValueError:
                            pass
                        final_entries.append(entry)
                    else:
                        final_entries.append(entry)
                else:
                    final_entries.append(entry)

            return final_entries
        except Exception as e:
            logging.warning(f"解析 AI JSON 结果失败: {e}，回退使用原始词条列表")
            return original_batch

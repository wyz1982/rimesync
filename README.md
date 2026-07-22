# Rime 远程词库同步与 OpenCode AI 智能调优系统 (rime-aisync)

轻量级、低开销的 Rime 输入法多端词库自动同步、异动合并与 AI Agent 智能调优引擎。专门针对 Armbian / Linux 低功耗服务器与 x86 服务器优化。

---

## 🌟 核心特性

1. **零额外 WebDAV 资源消耗**：直接适配您服务端已有的 WebDAV 服务，主服务无常驻内存开销。
2. **多端词库智能融合**：按 `installation_id` 自动隔离多端提交，采用加权衰减与对数平滑算法融合词频，防止单端误触污染。
3. **OpenCode CLI AI 双模式调优**：
   - **白天增量模式 (`--mode incremental`)**：快速抽取新增/异动词汇，进行拼音编码校验与音近/形近错别字拦截（建议每天运行 1~2 次）。
   - **晚间深度模式 (`--mode deep`)**：在夜间低峰期运行，执行全局语义消歧、频繁误触降频与高频短语提炼（建议每天深夜运行 1 次）。
4. **极高安全性与降级保护**：若 AI 服务未响应，系统会自动无缝回退至纯规则合并模式，保证词库数据 100% 安全不丢失。

---

## 📁 目录结构

```text
Rime_aisync_project/
├── config.json         # 系统配置文件（设置 WebDAV 目录、字典名称与规则）
├── rime_parser.py      # Rime userdb / custom_phrase 格式解析与生成器
├── rime_merger.py      # 多端词库合并、词频算法与增量提取引擎
├── ai_optimizer.py     # OpenCode CLI AI 调优适配模块（支持增量与深度 Prompt）
├── main.py             # CLI 主控制入口
├── install_cron.sh     # Armbian / Linux Cron 定时任务一键安装脚本
└── test_rime_sync.py   # 全流程单元与功能测试脚本
```

---

## 🚀 Armbian 服务器部署步骤

### 1. 配置文件 `config.json` 设置

修改 `config.json` 中的路径，指向您服务器上 WebDAV 服务的实际存储目录：

```json
{
  "sync_dir": "/var/webdav/rime/sync",
  "dist_dir": "/var/webdav/rime/sync/dist",
  "backup_dir": "/var/webdav/rime/backups",
  "opencode_bin": "opencode",
  "dict_names": ["rime_ice", "luna_pinyin"],
  "rules": {
    "min_freq_threshold": 1,
    "weight_decay": 0.9,
    "max_ai_batch_size": 30
  }
}
```

> **注意**：请确保 WebDAV 目录中各个客户端按 Rime 原生规范推送至 `sync/<installation_id>/` 子文件夹下。

### 2. 手动测试运行

```bash
# 测试 1: 仅做多端合并（不调用 AI）
python3 main.py --mode merge_only

# 测试 2: 执行白天增量调优
python3 main.py --mode incremental

# 测试 3: 执行晚间深度调优
python3 main.py --mode deep
```

优化后的统一词库文件将自动生成于 `dist_dir` 目录：
- `dist/rime_ice.userdb.txt`
- `dist/custom_phrase.txt`

### 3. 一键安装 Cron 定时任务

运行包含的定时任务安装脚本：

```bash
bash install_cron.sh
```

默认 Cron 策略：
- **白天增量调优**：每天 12:30 和 18:30 各运行一次。
- **晚间深度调优**：每天凌晨 03:00 运行一次。

---

## 📱 客户端配置指引 (Rime)

1. **设置 `installation_id`**：
   在各个客户端（Windows 小狼毫 / macOS 鼠须管 / Android 同文/仓）的 `default.custom.yaml` 中配置独立的 ID：
   ```yaml
   patch:
     "installation_id": "win-desktop"  # 移动端设为 "android-phone" 等
   ```
2. **WebDAV 同步**：
   在各端输入法中开启 WebDAV 同步，同步路径设置为服务器的 WebDAV 根目录。
3. **加载公共调优词库**：
   客户端可通过 WebDAV 挂载读取分发目录 `dist/custom_phrase.txt` 放在本地 Rime 用户文件夹下，重新部署即可享受到 AI 优化后的高频词与新词！

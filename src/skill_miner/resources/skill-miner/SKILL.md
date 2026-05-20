---
name: skill-miner
description: 当用户想从自己的 Claude Code 会话历史中挖掘重复出现的工作流、把高频操作沉淀为可复用 Skill 时使用。触发词例如"我都在重复做什么"、"分析我的历史"、"挖一下我的会话日志"、"哪些操作可以做成 skill"、"mine my history"、"find recurring workflows"。本地离线运行，不联网，不依赖任何外部模型。
metadata:
  source: skill-miner
---

## When to invoke

调用本 skill 的典型信号：

- 用户问"我最近在重复做什么"、"我有哪些高频操作"、"分析我的使用习惯"
- 用户想把已有工作流沉淀为 Skill，但不知道该写什么
- 用户明确提到扫描 `~/.claude/projects/` 下的会话日志
- 用户要求"挖掘 skill"、"mine skill / mine history / harvest workflow"

不要在以下场景使用：

- 用户只是想**手写**一个新的 Skill（用 `skill-creator` 而不是本 skill）
- 用户想**校验**已有 skill 的安全性（用 `skill-validator`）
- 用户的请求与他自己的会话历史无关

## Workflow

1. **扫描候选**

   ```bash
   skill-miner scan
   ```

   工具会读取 `~/.claude/projects/*/*.jsonl`，输出形如：

   ```
   id=a1b2c3d4e5  name=polish-academic-abstract  conf=0.78  evidence=12  sessions=5  status=proposed
   desc: 润色这段学术摘要的语言
   flow: Read:.md -> Edit:.md -> Bash:git
   ```

   候选会持久化到 `~/.claude/mined-skills/state.json`。

2. **展示候选给用户**

   ```bash
   skill-miner list        # 终端表格
   skill-miner report      # 写一份 markdown 报告到 ~/.claude/mined-skills/report-YYYY-MM-DD.md
   ```

   把候选列表展示给用户，重点说明：name、confidence、evidence 数量、tool flow、示例 prompt。让用户判断哪些值得保留。

3. **按用户意愿处置**

   ```bash
   skill-miner accept <id>     # 推到 ~/.claude/skills/<name>/SKILL.md
   skill-miner ignore <id>     # 标记忽略，下次 scan 不再打扰
   ```

   `accept` / `ignore` 的状态在重新 scan 时会保留。

4. **（可选）持续运行**

   如果用户希望以后每次 Claude Code 会话结束都自动重挖一遍：

   ```bash
   skill-miner install-hook
   ```

   会往 `~/.claude/settings.json` 注册一个 `Stop` hook。

## Notes for the agent

- **离线保证**：工具不联网、不调用任何 LLM、零运行时依赖。可以放心在任何环境下运行。
- **隐私**：输出已自动脱敏（邮箱、IP、Windows/POSIX 路径、`~/...`、`password=`/`token=` k/v、长字母数字串）。仍建议用户 accept 前自己看一眼 SKILL.md。
- **历史不足**：< 30 轮使用历史基本只能挖出噪音；置信度 < 0.25 的候选已被过滤。如果 `scan` 输出为空，提示用户多积累一些使用记录后再来。
- **接受前一定让用户审阅**：TF-IDF 聚类很朴素，可能把不相关的 prompt 合并。`report` 里的 `Examples:` 段就是用来判断这条到底是不是真工作流。
- **改名**：`accept` 后用户可以直接编辑 `~/.claude/skills/<name>/SKILL.md` 的 frontmatter，slugify 是贪心的，名字常常需要手调。

# skill-miner

> **从你自己的 Claude Code 会话历史里挖出可复用的 Skill。**
> 不需要 API key，不联网，你的 prompt 永不离开本机。

[![CI](https://github.com/xwmxcz/skill-miner/actions/workflows/ci.yml/badge.svg)](https://github.com/xwmxcz/skill-miner/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)]()

[English](README.md) · [中文](README.zh-CN.md)

---

每个 Claude Code 用户都在重复同样的事情：同样的代码 review 流程，同样的"帮我润色这段"，同样的 SSH 调试套路。问题是：你必须**自己注意到这个模式**，然后亲手把 Skill 写出来。

`skill-miner` 把这件事反过来做。它读取 Claude Code 已经写在 `~/.claude/projects/` 下的 JSONL 会话日志，找出反复出现的"prompt + 工具序列"组合，**自动为每种模式起草一份 `SKILL.md`**。你只需要审阅、接受、忽略。

## 为什么需要 skill-miner

现有 Skills 仓库——[`anthropics/skills`](https://github.com/anthropics/skills)、
[`tech-leads-club/agent-skills`](https://github.com/tech-leads-club/agent-skills) 等等——都把 Skill 当作**人类手写并发布的东西**。

`skill-miner` 把 Skill 当作**从你自己行为里收割出来的东西**。你不需要知道该写什么。重复本身就是答案。

|                              | 手写 Skills      | `skill-miner`                      |
| ---------------------------- | ---------------- | ---------------------------------- |
| 真相来源                     | 你以为你做了什么 | 你**实际上**做了什么               |
| 发现成本                     | 靠回忆和反思     | 1 秒扫描完成                       |
| 是否会过时                   | 会               | 每次会话结束自动重挖               |
| 联网 / API key               | 不需要           | **永远不需要**                     |
| 把你的 prompt 上传到任何地方 | 不会             | **不会，永远不会**                 |

## 安装

```bash
pip install -e .
```

需要 Python 3.10+。**零运行时依赖**——这不是愿望，是硬约束。

## 60 秒上手

```bash
# 1) 看看你最近在重复做什么
skill-miner scan
# [skill-miner] loaded 163 turns from 51 sessions
# [skill-miner] 5 raw candidate(s); 3 kept after filtering.
#
#   id=a1b2c3d4e5  name=polish-academic-abstract  conf=0.78  evidence=12  sessions=5
#   desc: 润色这段学术摘要的语言
#   flow: Read:.md -> Edit:.md -> Bash:git

# 2) 输出一份可以慢慢翻的 markdown 报告
skill-miner report
# -> ~/.claude/mined-skills/report-2026-05-20.md

# 3) 把候选 promote 成真正的 skill
skill-miner accept a1b2c3d4e5
# -> ~/.claude/skills/polish-academic-abstract/SKILL.md

# 4) 或者忽略它
skill-miner ignore a1b2c3d4e5

# 5) 每次 Claude Code 会话结束后自动重扫
skill-miner install-hook

# 6) 让 Claude Code 在你说"分析一下我都在做什么"时自动调用 skill-miner
skill-miner install-skill
```

## 工作原理

```
~/.claude/projects/*/*.jsonl
            │
            ▼
     ┌────────────┐    用户 prompt           ┌─────────────────────┐
     │  loader    │  ──────────────────────► │ TF-IDF + 余弦聚类   │
     │ (jsonl)    │                          │ 阈值 ≥ 0.35         │
     │            │  工具调用（标准化签名:   │ 中文走 CJK bigram   │
     │            │  Bash:git, Edit:.py,     └─────────┬───────────┘
     │            │  WebFetch...）                     │
     │            │                          ┌─────────▼───────────┐
     │            │  ──────────────────────► │ 3-5 元 n-gram 挖掘  │
     └────────────┘                          │ 跨会话出现 ≥ 3 次   │
                                             └─────────┬───────────┘
                                                       │
                                             ┌─────────▼───────────┐
                                             │  关联                │
                                             │  prompt 簇 ↔ n-gram │
                                             │  → 启发式置信度     │
                                             └─────────┬───────────┘
                                                       │
                                             ┌─────────▼───────────┐
                                             │  脱敏 PII +          │
                                             │  渲染 SKILL.md       │
                                             └─────────────────────┘
```

对 `~/.claude/projects/` 下的每个 `*.jsonl`：

1. **用户 prompt** 走分词 → TF-IDF 向量化 → 余弦相似度（≥ 0.35）聚类。中文用重叠 CJK bigram 处理。问候语、slash 命令标记、`[Request interrupted]` 噪音、context compaction 摘要全部丢弃。
2. **工具调用** 折叠成标准签名（`Bash:git`、`Edit:.py`、`WebFetch` ……），然后挖掘跨会话出现 ≥ 3 次的 3-5 元序列。
3. **关联** —— 每个 prompt 簇与最集中出现在它会话里的工具 n-gram 配对。给出启发式置信度（`0..1`）。

每个存活的 pair 会渲染成一份 `SKILL.md` 草稿，包含：

- 从簇关键词派生的 slug（中文-only 簇会回退到工具流，例如 `read-edit-bash`）
- 脱敏过的描述，加上 2-3 条来自你历史的示例 prompt
- 典型工具序列（代码块）

## 隐私

本工具**有意离线**：

- ✅ 只读你磁盘上已有的文件
- ✅ 零运行时依赖；什么都不会回家
- ✅ 输出只写在 `~/.claude/mined-skills/` 和 `~/.claude/skills/` 下
- ✅ 自动脱敏邮箱、IP、文件路径、`~/...` 路径、`password=` / `token=` 模式、像密钥的长字母数字串。**写入时脱敏，每次保存还会再脱一遍**——历史遗留数据也会被清理

如果正则漏了什么明显敏感的内容，请提个 issue，**重现样本里不要带真实密钥**。

## FAQ

**Q：我扫描完一条候选都没有，是不是坏了？**
没坏。门槛（`min_count >= 3`、`min_cluster_size >= 3`、`confidence >= 0.25`）刻意设得保守，就是为了避免噪音。如果你只有 < 30 轮历史，看不到东西是正常的。多用一段时间 Claude Code 再扫。

**Q：候选挖出来的 tool flow 跟 prompt 对不上怎么办？**
TF-IDF 聚类是故意保持简单的。有时候真实 prompt 簇会跟一个恰好在同样 session 里频繁出现但跟意图无关的 n-gram 配对。**接受前一定先看 `report` 里的 Examples 段**——这正是它存在的理由。

**Q：为什么不用 embedding 模型？为什么不调 LLM？**
因为 `pip install` 一个 500 MB 的模型，或者要 API key 才能跑，会劝退一半受众。v0.1 的硬约束是**只用标准库，能在任何 Python 3.10+ 上跑**。更好的排序是 roadmap 里的可选 extra。

**Q：`accept` 会覆盖我手动改过的 `~/.claude/skills/<name>/SKILL.md` 吗？**
会。`accept` 总是直接写文件。如果你已经手改过某个之前接受的 skill，先把它备份到别处，或者 `skill-miner ignore <id>`。

**Q：重新扫描会不会清掉我之前 `accept` / `ignore` 的决定？**
不会。状态用 `sha1(name || ngram)[:10]` 作为 key。只要候选的 name + tool flow 没变，你的决定就跨扫描保留。

**Q：我在 Windows 上看 report 出现乱码？**
CLI 内部已经调了 `sys.stdout.reconfigure(encoding="utf-8")`。如果你看 `state.json` 是乱的，说明你用的工具忽略了 UTF-8 BOM-less 声明。VS Code 或任何尊重 UTF-8 的编辑器都能正常打开。

## 已知限制（alpha）

- 适合至少一周 Claude Code 使用历史的用户。< 30 轮基本只能产生噪音。
- TF-IDF 聚类可能把词汇重叠的不相关 prompt 合并到一起。
- 置信度是启发式分数，不是概率。
- Slug 是贪心生成的，accept 后通常需要手动改 frontmatter。

## Roadmap

- [ ] 可选的 `--with-embeddings` extra，提升聚类质量
- [ ] 重新挖掘时的 side-by-side diff（自上次扫描以来有什么新东西？）
- [ ] 多机合并（笔记本 + 工作站各跑一次，候选取并集）
- [ ] 更聪明的 Bash 命令签名（提取重复出现的 `--flag` 形状，不只是头部程序名）
- [ ] 支持 n-gram **gap-gram**（例如 `Read:.rs → ??? → Bash:cargo`），覆盖中间步骤变化的工作流

## 贡献

欢迎 issue 和 PR。除非你贡献的是（未来的）`--with-embeddings` extra，否则**零运行时依赖**这条规则不能破。

```bash
pip install -e .[dev]
pytest -q
```

版本变更见 [CHANGELOG.md](CHANGELOG.md)。

## License

MIT。见 [LICENSE](LICENSE)。

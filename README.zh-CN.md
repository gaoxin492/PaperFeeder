<h1 align="left">
  <img src=".github/assets/icon.png" alt="PaperFeeder icon" width="44" style="vertical-align: middle; margin-right: 10px;" />
  <span style="vertical-align: middle;">PaperFeeder（中文说明）</span>
</h1>

> A research intelligence agent pipeline for daily paper and blog triage to your email inbox.

PaperFeeder 是围绕 inbox workflow 设计的：研究简报主要通过邮件交付，网页查看、manifest 和 feedback 流水线则用于补充审阅、回看与反馈收集。

> 英文版说明见 [README.md](README.md)。

## 界面预览

<table>
  <tr>
    <td align="center"><img src=".github/assets/1.png" alt="Digest overview" width="260" /></td>
    <td align="center"><img src=".github/assets/2.png" alt="Blog pick detail" width="260" /></td>
  </tr>
  <tr>
    <td align="center"><strong>1.</strong> 总览页</td>
    <td align="center"><strong>2.</strong> 博客精选详情</td>
  </tr>
  <tr>
    <td align="center"><img src=".github/assets/3.png" alt="Paper pick detail" width="260" /></td>
    <td align="center"><img src=".github/assets/4.png" alt="Judgment summary" width="260" /></td>
  </tr>
  <tr>
    <td align="center"><strong>3.</strong> 论文精选详情</td>
    <td align="center"><strong>4.</strong> 今日判断摘要</td>
  </tr>
</table>

### 自动化预览

如果你希望 PaperFeeder 更像一个每天自动运行的远程服务，而不是手动执行的本地脚本，GitHub Actions 是默认主路径。

<p align="center">
  <img src=".github/assets/github_action.png" alt="GitHub Actions 定时工作流界面" width="960" />
</p>

## 为什么用 PaperFeeder

PaperFeeder 不是一个简单的“论文订阅脚本”，而是一套面向研究者、研究团队和 AI Lab 的轻量研究情报系统。它的目标不是再给你一个需要经常打开的 dashboard，而是把高信号研究简报直接送进你的邮箱。

它要解决的不是“帮你收集更多链接”，而是：

1. 每天从高噪声信息流里提炼出少量真正值得看的内容
2. 让 digest 不只是摘要，而是带判断、带优先级、带上下文的研究简报
3. 让系统能记住你最近已经看过什么
4. 让系统能根据你的显式反馈逐步校准未来推荐
5. 既能本地开发调试，也能远程自动化托管

这里有一个关键产品选择：邮件不是附属通知层，而是研究简报的主要交付方式，其他组件都围绕这条工作流展开。

为什么它不只是“RSS + 总结”：

| 层级 | 带来的能力 |
|------|------------|
| 多源采集 | 同时覆盖 arXiv、Hugging Face Daily Papers、Semantic Scholar 推荐、优先博客、手动源 |
| 多阶段筛选 | 关键词过滤、coarse LLM filter、外部信号增强、fine reranking |
| PDF 感知摘要 | 有 PDF 时尽量基于全文前若干页，而不只看标题和 abstract |
| 状态化个性化 | 短期 memory 与长期 seeds 分离，分别处理新鲜度与偏好 |
| 显式反馈闭环 | 👍 / 👎 最终会写回未来推荐输入，而不是停留在 UI 按钮层 |
| 可部署运维 | 支持本地 dry-run、debug fixture、GitHub Actions、Cloudflare Worker + D1 |

核心能力一览：

| 能力 | 说明 |
|------|------|
| 个性化候选生成 | 通过 `user/` 下的人设、关键词、排除词、arXiv 分类、博客源控制候选池 |
| Semantic Scholar 个性化 | 正负 seeds 影响后续推荐抓取 |
| Anti-repetition memory | `state/semantic/memory.json` 抑制最近重复出现的内容 |
| 两阶段 LLM 筛选 | 第一阶段快速缩池，第二阶段结合外部信号精排 |
| 外部信号增强 | Tavily 增加代码实现、社区讨论、可复现性等线索 |
| 更扎实的 digest 生成 | 支持 PDF 输入、prompt language packs、HTML 邮件与网页输出 |
| 单条反馈闭环 | 邮件和网页中的 👍 / 👎 会进入 Worker + D1，再写回 seeds |
| 运行可追溯 | 每次运行会导出 manifest/template 到 `artifacts/` |

## 系统如何工作

PaperFeeder 刻意把“候选生成、筛选、报告、去重、偏好学习”拆成独立层，而不是混在一个黑箱里。

### 完整方法链路

1. 从论文源和博客源抓取候选内容。
2. 用关键词与排除词做第一层过滤。
3. 用 coarse LLM filter 基于 title 和 abstract 快速缩小候选集。
4. 用 Tavily 给入围论文补外部信号。
5. 用 fine LLM filter 决定真正值得进入报告的内容。
6. 有 PDF 时读取全文前若干页并生成 digest。
7. 发送邮件，并可选发布网页版本。
8. 把本次真正出现在报告里的内容写入短期 memory。
9. 把显式 👍 / 👎 反馈写回长期 seeds，影响未来推荐。

### 状态模型

| 状态 | 文件 / 存储 | 作用 |
|------|-------------|------|
| 短期记忆 | `state/semantic/memory.json` | 抑制近期重复出现的内容，保证 digest 新鲜度 |
| 长期偏好 | `state/semantic/seeds.json` | 存储正负 Semantic Scholar seed IDs，用来引导未来推荐 |
| 每次运行产物 | `artifacts/run_feedback_manifest_*.json`、`artifacts/semantic_feedback_template_*.json` | 记录本次报告与反馈映射，方便审计与离线反馈 |
| 远程反馈队列 | Cloudflare D1 | 暂存待应用的 👍 / 👎 事件 |

关键区别是：

1. `memory.json` 表示“最近看过，先少推一点”
2. `seeds.json` 表示“以后多推这种 / 少推这种”

它们都不会改模型参数，只会改变候选集合和推荐输入。

### 仓库结构

```text
PaperFeeder/
├── paperfeeder/          # 主 Python 包
├── scripts/              # 一键安装与反馈辅助脚本
├── cloudflare/           # Worker 源码与 D1 schema
├── state/semantic/       # 持久化 memory 和 seeds
├── artifacts/            # 每次运行导出的 manifest/template
├── user/                 # 用户可编辑的人设、关键词、提示词和博客源
├── tests/                # 测试集
├── config.yaml           # 主配置文件
├── icon.png              # README / 项目图标
└── main.py               # 主入口
```

关键模块：

1. `paperfeeder/pipeline/runner.py`：串起整个 pipeline
2. `paperfeeder/pipeline/filters.py`：关键词过滤与 coarse/fine LLM 筛选
3. `paperfeeder/pipeline/summarizer.py`：摘要生成与 HTML 报告包装
4. `paperfeeder/pipeline/researcher.py`：Tavily 外部信号增强
5. `paperfeeder/semantic/memory.py`：短期 anti-repetition memory
6. `paperfeeder/cli/apply_feedback.py`：把离线反馈、队列反馈或 D1 反馈写回 seeds
7. `cloudflare/feedback_worker.js`：反馈收集与网页查看入口

## 本地配置与运行

### 需要什么

| 组件 | 是否必需 | 作用 |
|------|----------|------|
| LLM API | 必需 | 生成 digest，且在启用时参与 LLM 筛选 |
| 邮件服务 | 本地预览非必需，真实使用基本必需 | 用系统设计的主形态把 digest 送进邮箱 |
| Tavily API | 可选但推荐 | 外部信号增强 |
| Semantic Scholar API | 强烈推荐 | 改善 semantic ID 解析和 feedback 按钮可用率 |
| Cloudflare Worker + D1 | 可选 | 开启 one-click feedback 闭环 |

### 成本轮廓

PaperFeeder 的一条设计原则就是：成本要可控，而不是把所有步骤都堆到同一个贵模型上。

核心原因是它把不同阶段拆开了：

1. coarse / fine filter 可以用很便宜的模型，例如 DeepSeek
2. 最终 digest 的理解、判断和写作，再交给更强的 Claude、Gemini 或 GPT API
3. 贵模型处理的是 shortlist，而不是整条高噪声信息流
4. PDF 感知摘要也是可选项，而且有页数上限，不会随原始候选数线性暴涨

实际运行里，便宜的是筛选，真正占大头的是最后那一步 synthesis；而那一步面对的是已经缩小过的一小组内容，所以整体花销通常不高。

一个很粗略的 LLM 月度成本估算，可以按下面这个量级理解：假设每天跑 1 次，每天原始候选大约 40 到 60 条，进入 LLM filter 的大约 15 到 25 条，最终 shortlist 大约 6 到 10 条，PDF 阅读限制在前 10 到 15 页。

| 档位 | 典型模型分工 | 粗略月成本 |
|------|--------------|-----------|
| 预算档 | DeepSeek 做筛选 + Gemini Flash 或其他低价模型做最终 digest | 约 $2 到 $8 / 月 |
| 平衡档 | DeepSeek 做筛选 + Claude Sonnet / Gemini Pro / GPT 级模型做最终 digest | 约 $8 到 $25 / 月 |
| 重度档 | 每天都用较贵模型做 synthesis，且 PDF 更多、shortlist 更长 | 约 $20 到 $50 / 月 |

这只是数量级粗估，不是精确报价。真实花销主要取决于：

1. 有多少内容能通过关键词过滤进入 LLM 阶段
2. 是否开启 PDF-aware synthesis
3. 最终 digest 选用什么模型
4. 运行频率是多少

对个人研究者或小团队来说，这套系统通常便宜到足以把“模型选型”当成质量选择，而不是基础设施负担。Tavily、邮件服务和 Cloudflare 这类可选组件的费用是分开的，在低频使用下通常也不高。

### 本地配置步骤

```bash
bash scripts/bootstrap.sh
source .venv/bin/activate
```

然后：

1. 把 `.env.example` 复制成 `.env`
2. 填入本地使用的 LLM、邮件、可选 feedback 服务凭证
3. 修改 `config.yaml` 里的开关、限制和路径
4. 修改 `user/blogs.yaml` 里的博客源
5. 修改 `user/` 下面的人设、关键词、排除词、分类和 prompt addon

本地 `.env` 只服务于本地开发 / 本地测试。GitHub Actions 远程部署应当使用 GitHub Secrets / Variables，不依赖仓库里的 `.env`。

如果你只记住一条配置原则，那就是：本地预览只是调试手段，真正的产品体验是稳定的邮箱投递。

### 用户主要会改哪些文件

| 文件 | 控制什么 |
|------|----------|
| `config.yaml` | 运行开关、抓取窗口、路径设置、prompt language、状态行为 |
| `user/blogs.yaml` | 博客源选择和自定义 RSS |
| `user/research_interests.txt` | 研究画像 / 长文本兴趣描述 |
| `user/keywords.txt` | 正向关键词 |
| `user/exclude_keywords.txt` | 噪音主题排除词 |
| `user/arxiv_categories.txt` | arXiv 分类范围 |
| `user/prompt_addon.txt` | 附加 prompt 指令 |

配置优先级：

1. `config.yaml`
2. `user/blogs.yaml`
3. 环境变量
4. `user/research_interests.txt`、`user/prompt_addon.txt`、`user/keywords.txt`、`user/exclude_keywords.txt`、`user/arxiv_categories.txt`

预设 profile 在 `user/examples/profiles/` 下面。

### 常用命令

主 digest：

```bash
python main.py --dry-run
python main.py --days 3
```

示例运行历史：

```bash
================================================================================
PaperFeeder - 2026-03-21 21:40
================================================================================
Fetching from arXiv...
    Querying: cat:cs.LG OR cat:cs.CL OR cat:cs.AI...
    (arXiv API can be slow, ~10-60s, please wait...)
    ✓ Response received, reading data...
    ✓ Got 701986 bytes, parsing XML...
  Found 0 papers
Fetching from HuggingFace Daily Papers...
    Trying: https://huggingface.co/api/daily_papers...
    ✓ Response received, parsing...
    HuggingFace suppression: total=50, suppressed=13, forwarded=37
  Found 37 papers
Fetching from Semantic Scholar recommendations...
    📉 Semantic Scholar suppression: total=20, suppressed=11, forwarded=9
  Found 9 papers
  Semantic Scholar stats: total=20, suppressed=11, forwarded=9
Total unique papers: 46
Fetching from blogs...
📝 Fetching from 9 blogs...
  ✓ Hugging Face Blog: 4 posts
  ⚠️ Meta Research: HTTP 400
  ✓ OpenAI Blog: 5 posts
  ⚠️ Anthropic News & Research: HTTP 404
  ✓ Google DeepMind: 1 posts
  ✅ Found 10 blog posts (10 priority, 0 normal)
  Priority blogs (skip filter): 10
  Normal blogs (go through filter): 0

Filtering 46 papers...
  Keyword filter: 19 papers matched
  LLM Filter [Coarse (title+abstract)]: Processing 19 papers in 2 batches
  Batch 1/2 (10 papers)...
  Batch 2/2 (9 papers)...
  Scored 16 papers, sorting by relevance...
  LLM coarse filter: 16 papers selected for enrichment
  Using Tavily API for research

Researching 16 papers for external signals...
  [1/16] Researching: SAMA: Factorized Semantic Anchoring and Motion Ali...
  [2/16] Researching: ReasonCACHE: Teaching LLMs To Reason Without Weigh...
  [3/16] Researching: ReflexiCoder: Teaching Large Language Models to Se...
  [4/16] Researching: What Really Controls Temporal Reasoning in Large L...
  [5/16] Researching: Video-CoE: Reinforcing Video Event Prediction via ...
  [6/16] Researching: AI Scientist via Synthetic Task Scaling...
  [7/16] Researching: Reinforcement-aware Knowledge Distillation for LLM...
  [8/16] Researching: Goldilocks RL: Tuning Task Difficulty to Escape Sp...
  [9/16] Researching: Curriculum Learning for Efficient Chain-of-Thought...
  [10/16] Researching: Self-Distillation Enables Continual Learning...
  [11/16] Researching: Fanar-Sadiq: A Multi-Agent Architecture for Ground...
  [12/16] Researching: Temporal Gains, Spatial Costs: Revisiting Video Fi...
  [13/16] Researching: Expanding the Capabilities of Reinforcement Learni...
  [14/16] Researching: Doc-to-LoRA: Learning to Instantly Internalize Con...
  [15/16] Researching: OSM-based Domain Adaptation for Remote Sensing VLM...
  [16/16] Researching: BenchPreS: A Benchmark for Context-Aware Personali...
  Research complete: 16 papers enriched
  LLM Filter [Fine (with community signals)]: Processing 16 papers in 2 batches
  Batch 1/2 (10 papers)...
  Batch 2/2 (6 papers)...
  Scored 9 papers, sorting by relevance...
  LLM fine filter: selected 9 papers for final report
  Processing 9 PDFs individually...
    [1/9] ReasonCACHE: Teaching LLMs To Reason Wit...
    PDF download failed for https://arxiv.org/pdf/2602.02366.pdf...:
    [2/9] Goldilocks RL: Tuning Task Difficulty to...
    Extracted first 15 pages (total: 21)
    PDF processed: 718403 bytes -> base64 length: 957872
    [3/9] Curriculum Learning for Efficient Chain-...
    PDF download failed for https://arxiv.org/pdf/2602.17686.pdf...:
    [4/9] Temporal Gains, Spatial Costs: Revisitin...
    Extracted first 15 pages (total: 18)
    PDF processed: 2732551 bytes -> base64 length: 3643404
    [5/9] Self-Distillation Enables Continual Lear...
    Extracted first 15 pages (total: 21)
    PDF processed: 1079504 bytes -> base64 length: 1439340
    [6/9] Doc-to-LoRA: Learning to Instantly Inter...
    Extracted first 15 pages (total: 28)
    PDF processed: 562264 bytes -> base64 length: 749688
    [7/9] BenchPreS: A Benchmark for Context-Aware...
    PDF download failed for https://arxiv.org/pdf/2603.16557.pdf...:
    [8/9] Reinforcement-aware Knowledge Distillati...
    PDF has 13 pages (using all)
    PDF processed: 488497 bytes -> base64 length: 651332
    [9/9] OSM-based Domain Adaptation for Remote S...
    PDF download failed for https://arxiv.org/pdf/2603.11804.pdf...:
  Feedback manifest exported: artifacts/run_feedback_manifest_2026-03-21T13-49-26Z.json
  Feedback questionnaire template exported: artifacts/semantic_feedback_template_2026-03-21T13-49-26Z.json
  Published web viewer report to D1
  Semantic memory updated: final_selected=9, report_visible=4, seen_keys_added=12, expired_removed=0
  Email sent successfully

Pipeline complete
  Papers fetched: 46
  Blogs fetched: 10
  After keyword filter: 16
  After enrichment: 16
  Final papers: 9
  Total in report: 19
```

固定 JSON 调试：

```bash
python main.py --debug-sample --dry-run
python main.py --debug-sample
python main.py --debug-sample --debug-llm-report --dry-run
python main.py --debug-minimal-report --dry-run
python main.py --debug-sample --debug-sample-path path/to/papers.json --dry-run
```

可选：`--debug-write-memory` 会在 debug sample 模式下更新 `state/semantic/memory.json`。

把 manifest 对应的反馈写回 seeds：

```bash
python -m paperfeeder.cli.apply_feedback --manifest-file artifacts/run_feedback_manifest_<run_id>.json --dry-run
python -m paperfeeder.cli.apply_feedback --manifest-file artifacts/run_feedback_manifest_<run_id>.json
```

从 Cloudflare D1 拉待处理反馈：

```bash
python -m paperfeeder.cli.apply_feedback --from-d1 --manifest-file artifacts/run_feedback_manifest_<run_id>.json --manifests-dir artifacts --dry-run
python -m paperfeeder.cli.apply_feedback --from-d1 --manifest-file artifacts/run_feedback_manifest_<run_id>.json --manifests-dir artifacts
```

也可以用脚本包装：

```bash
python scripts/semantic_feedback_apply.py --manifest-file artifacts/run_feedback_manifest_<run_id>.json --dry-run
```

## 远程自动部署（GitHub Actions）

如果你想把 PaperFeeder 当成一个远程服务来跑，GitHub Actions 是主部署路径。实际意义上，它就是把这套系统变成“每天自动投递到邮箱的研究简报服务”。

### 两个 workflow 分别做什么

| Workflow | 作用 |
|----------|------|
| `.github/workflows/daily-digest.yml` | 定时跑 digest、发邮件、持久化 `memory.json` |
| `.github/workflows/apply-feedback-queue.yml` | 定期把 D1 里的反馈合并进 `seeds.json` |

### 需要哪些 Secrets / Variables

最小远程邮件部署所需 Secrets：

1. `LLM_API_KEY`
2. `LLM_MODEL`
3. `RESEND_API_KEY`
4. `EMAIL_TO`

常见扩展 Secrets：

1. `LLM_BASE_URL`
2. `LLM_FILTER_API_KEY`
3. `LLM_FILTER_BASE_URL`
4. `LLM_FILTER_MODEL`
5. `TAVILY_API_KEY`
6. `SEMANTIC_SCHOLAR_API_KEY`
7. `CLOUDFLARE_ACCOUNT_ID`
8. `CLOUDFLARE_API_TOKEN`
9. `D1_DATABASE_ID`
10. `FEEDBACK_ENDPOINT_BASE_URL`
11. `FEEDBACK_LINK_SIGNING_SECRET`

推荐 Variables：

1. `SEED_STATE_BRANCH`
2. `SEMANTIC_MEMORY_ENABLED`
3. `SEMANTIC_SEEN_TTL_DAYS`
4. `SEMANTIC_MEMORY_MAX_IDS`
5. `FEEDBACK_TOKEN_TTL_DAYS`
6. `FEEDBACK_REVIEWER`

### 当前默认时间

| Workflow | UTC | 北京时间 |
|----------|-----|----------|
| `daily-digest.yml` | `1 0 * * *` | 每天早上 08:01 |
| `apply-feedback-queue.yml` | `30 16 */3 * *` | 每 3 天凌晨 00:30（次日） |

GitHub Actions 的 cron 是基于 UTC 日历时间，不是严格的每 72 小时定时器。像 `*/3` 这种写法会在跨月时按日历重新开始。

### 首次远程部署步骤

1. 把仓库推到 GitHub 并开启 Actions
2. 在仓库设置里补齐 Secrets / Variables
3. 手动执行一次 `Daily Paper Digest`，先用 `dry_run=true`
4. 检查日志和 artifacts
5. 再执行一次 `dry_run=false`
6. 确认 state branch 已创建并开始更新

state branch 的设计：

1. workflow 不会把运行状态写回 `main`
2. 默认使用独立分支 `memory-state`
3. 这个分支存 `state/semantic/memory.json` 和 `state/semantic/seeds.json`

### 两种远程模式

只要“每天自动发邮件”的最小模式：

1. `LLM_*`
2. `RESEND_API_KEY`
3. `EMAIL_TO`
4. `daily-digest.yml`

完整闭环模式：

1. 上面全部内容
2. Cloudflare Worker
3. D1
4. `apply-feedback-queue.yml`

完整模式下的闭环是：

1. `daily-digest.yml` 发出 digest
2. 用户通过邮件或网页里的链接提交反馈
3. 事件进入 D1
4. `apply-feedback-queue.yml` 把它们写回 `seeds.json`
5. 后续 Semantic Scholar 推荐随之变化

## 运行测试

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

## 其他说明

1. `artifacts/` 和 `llm_filter_debug/` 都是运行产物目录。
2. GitHub Actions 会在 state branch 上持久化 `state/semantic/seeds.json` 和 `state/semantic/memory.json`。
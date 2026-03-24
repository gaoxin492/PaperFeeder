<h1 align="left">
  <img src=".github/assets/icon.png" alt="PaperFeeder icon" width="44" style="vertical-align: middle; margin-right: 10px;" />
  <span style="vertical-align: middle;">PaperFeeder（中文说明）</span>
</h1>

> 每日论文与博客情报流水线，把高信噪比研究摘要直接送进你的邮箱。

> 英文版说明见 [README.md](README.md)。

## 界面预览

<table>
  <tr>
    <td align="center"><img src=".github/assets/1.png" alt="Overview and blog picks" width="195" /></td>
    <td align="center"><img src=".github/assets/2.png" alt="Paper pick detail 1" width="195" /></td>
    <td align="center"><img src=".github/assets/3.png" alt="Paper pick detail 2" width="195" /></td>
    <td align="center"><img src=".github/assets/4.png" alt="Judgment summary" width="195" /></td>
  </tr>
  <tr>
    <td align="center"><strong>1.</strong> 总览页 + 博客精选</td>
    <td align="center"><strong>2.</strong> 论文精选详情</td>
    <td align="center"><strong>3.</strong> 论文精选详情</td>
    <td align="center"><strong>4.</strong> 今日判断摘要</td>
  </tr>
</table>

<p align="center">
  <img src=".github/assets/github_action.png" alt="GitHub Actions 定时工作流界面" width="960" />
</p>

## 工作原理

PaperFeeder 每天（或按需）跑一次多阶段流水线，生成带判断的 HTML 摘要并通过邮件投递。

### 流水线各阶段

```
数据源 → 关键词过滤 → Coarse LLM 过滤 → 外部信号增强 → Fine LLM 过滤 → 生成摘要 → 发邮件
```

1. **抓取** — 从 arXiv、Hugging Face Daily Papers、Semantic Scholar 推荐和精选博客拉取候选内容
2. **关键词过滤** — 去掉不符合兴趣关键词或命中排除词的条目
3. **Coarse LLM 过滤** — 用便宜的模型批量对 title + abstract 打分，快速缩小候选集
4. **外部信号增强** — 用 Tavily 搜索每篇论文的代码实现、社区讨论、可复现性等信号
5. **Fine LLM 过滤** — 结合外部信号对 shortlist 再精排；决定最终进入报告的内容
6. **生成摘要** — 用强模型生成带判断的 HTML 报告，可选读取 PDF 全文前若干页
7. **投递** — 发送邮件；可选把网页版推送到 Cloudflare D1

### 双模型架构

流水线刻意把筛选和最终生成拆成两个 LLM 角色，便宜模型处理大量候选，强模型只面对 shortlist：

| 角色 | 环境变量 | 推荐模型 |
|------|----------|---------|
| Coarse + fine 过滤 | `LLM_FILTER_*` | 便宜模型（如 DeepSeek） |
| 最终摘要写作 | `LLM_*` | 强模型（如 Claude、Gemini、GPT-4o） |

如果没有设置 `LLM_FILTER_*`，筛选阶段也会使用主模型。

### 状态模型

| 状态 | 位置 | 作用 |
|------|------|------|
| 短期记忆 | Cloudflare D1 + `state/semantic/memory.json` | D1 是远程真相源；本地 JSON 是可导出、可编辑的镜像 |
| 长期偏好 | Cloudflare D1 + `state/semantic/seeds.json` | D1 是远程真相源；本地 JSON 是可导出、可编辑的镜像 |
| 每次运行产物 | `artifacts/` | 每次运行的 feedback manifest 和审阅模板 |
| 远程反馈队列 | Cloudflare D1 | 暂存待处理的 👍/👎 事件 |

两个状态文件的区别：
- `memory.json` — "最近已看过，暂时跳过"
- `seeds.json` — "以后多推/少推这类论文"

运行上以 D1 作为共享远程状态，本地文件只作为按需导出、编辑、再导入的工作副本。

### 反馈闭环

```
每日摘要 → 读者在邮件或网页里点击 👍/👎
→ Cloudflare Worker 把事件写入 D1
→ apply-feedback-queue.yml 把事件合并到 D1 支撑的 seeds 状态
→ 后续 Semantic Scholar 推荐随之调整
```

## 仓库结构

```
PaperFeeder/
├── paperfeeder/           # 主 Python 包
│   ├── pipeline/          # 流水线各阶段（runner、filters、researcher、summarizer）
│   ├── sources/           # 论文和博客抓取器（arXiv、HF、Semantic Scholar、RSS）
│   ├── semantic/          # Memory store、feedback 导出、链接签名
│   ├── cli/               # CLI 命令（apply_feedback、export_state、import_state、reset_memory）
│   ├── config/            # 配置加载与 schema
│   ├── chat.py            # OpenAI 兼容的 LLM 客户端
│   └── email.py           # 邮件后端（Resend、SendGrid、文件、控制台）
├── cloudflare/            # Cloudflare Worker 源码与 D1 schema
├── scripts/               # 一键安装与反馈辅助脚本
├── state/semantic/        # 运行时状态（memory.json、seeds.json）
├── artifacts/             # 每次运行导出的 manifest 和模板
├── user/                  # 用户可编辑的人设、关键词、博客源、prompt addon
├── config.yaml            # 主配置文件
└── main.py                # 摘要入口
```

关键模块：

| 文件 | 作用 |
|------|------|
| `paperfeeder/pipeline/runner.py` | 串起整个流水线 |
| `paperfeeder/pipeline/filters.py` | 关键词过滤与两阶段 LLM 筛选 |
| `paperfeeder/pipeline/researcher.py` | Tavily 外部信号增强 |
| `paperfeeder/pipeline/summarizer.py` | LLM 摘要生成与 HTML 包装 |
| `paperfeeder/semantic/memory.py` | Anti-repetition memory store |
| `paperfeeder/cli/apply_feedback.py` | 把离线/队列/D1 反馈写回 seeds |
| `cloudflare/feedback_worker.js` | 反馈收集与网页查看端点 |

## 本地配置与运行

### 需要什么

| 组件 | 是否必需 | 说明 |
|------|----------|------|
| LLM API | 必需 | 任意 OpenAI 兼容接口 |
| 邮件服务 | 真实使用必需 | 默认 Resend；本地 dry-run 时保存为文件 |
| Tavily API | 推荐 | 外部信号增强 |
| Semantic Scholar API key | 推荐 | 更好的 ID 解析和推荐质量 |
| Cloudflare Worker + D1 | 可选 | one-click 反馈闭环 |

### 安装

```bash
bash scripts/bootstrap.sh
source .venv/bin/activate
```

然后：

1. 把 `.env.example` 复制成 `.env` 并填入凭证
2. 编辑 `config.yaml` 调整开关、限制和模型配置
3. 编辑 `user/` 下的文件填入研究兴趣、关键词和博客源

`.env` 仅用于本地开发。GitHub Actions 部署应使用 Repository Secrets 和 Variables，不依赖 `.env`。

### 用户可编辑文件

| 文件 | 控制内容 |
|------|----------|
| `config.yaml` | 所有运行开关、抓取窗口、模型选项、状态路径 |
| `user/research_interests.txt` | 研究画像，注入到 LLM prompt |
| `user/keywords.txt` | 正向匹配关键词（title/abstract） |
| `user/exclude_keywords.txt` | 排除词 |
| `user/arxiv_categories.txt` | 监控的 arXiv 分类 |
| `user/blogs.yaml` | 启用的博客源和自定义 RSS |
| `user/prompt_addon.txt` | 额外注入到 LLM prompt 的指令 |

预设 profile 在 `user/examples/profiles/` 下面。

### 常用命令

```bash
# 标准运行
python main.py --dry-run          # 跑流水线，报告保存到文件（不发邮件）
python main.py --days 3           # 使用 3 天回看窗口

# 调试模式（跳过实时拉取/筛选/增强，快速迭代 prompt）
python main.py --debug-sample --dry-run              # 加载 fixture，跳过所有实时阶段
python main.py --debug-sample --debug-llm-report     # fixture + 调用 LLM 生成报告
python main.py --debug-minimal-report --dry-run      # 拉取真实论文，用 stub 报告
```

任意调试运行加上 `--debug-write-memory` 可同时更新 `state/semantic/memory.json`。

把反馈写回 seeds：

```bash
# 从本地 manifest 文件
python -m paperfeeder.cli.apply_feedback \
  --manifest-file artifacts/run_feedback_manifest_<run_id>.json --dry-run

# 从 Cloudflare D1 拉取所有待处理事件
python -m paperfeeder.cli.apply_feedback \
  --from-d1 --manifests-dir artifacts --dry-run
```

本地管理 D1 支撑的 semantic state：

```bash
# 把远程状态拉到本地 JSON 镜像
./scripts/export-state

# 本地编辑长期偏好 seeds
./scripts/edit-seeds

# 把本地 JSON 镜像重新推回 D1
./scripts/import-state

# 清空短期记忆（本地 + D1）
./scripts/reset-memory --yes
```

如果你更喜欢显式 Python 入口，也可以直接运行：

```bash
python -m paperfeeder.cli.export_state
python -m paperfeeder.cli.edit_seeds
python -m paperfeeder.cli.import_state
python -m paperfeeder.cli.reset_memory --yes
```

推荐工作流：

1. 先执行 `./scripts/export-state`，把 D1 里的最新状态同步到本地。
2. 用 `./scripts/edit-seeds` 打开 `state/semantic/seeds.json`。
3. 编辑完成后执行 `./scripts/import-state --only seeds` 回写远程状态。
4. 需要清空近期去重窗口时执行 `./scripts/reset-memory --yes`。

重置本地运行状态：

```bash
python -m paperfeeder.cli.reset_runtime_state --yes              # 清空 memory.json + 本地队列
python -m paperfeeder.cli.reset_runtime_state --yes --with-seeds # 同时清空 seeds.json
python -m paperfeeder.cli.reset_runtime_state --yes --skip-queue # 只清 memory
```

## 远程自动部署（GitHub Actions）

两个 workflow 分工如下：

| Workflow | 计划时间（UTC） | 北京时间 | 作用 |
|----------|--------------|---------|------|
| `daily-digest.yml` | `1 0 * * *` | 08:01 每天 | 跑流水线、发邮件、更新 memory |
| `apply-feedback-queue.yml` | `30 16 */3 * *` | 00:30，每 3 天 | 把 D1 反馈合并到 seeds |

### Secrets 和 Variables 配置

所有 secrets 放在 **Settings → Secrets and variables → Actions → Repository secrets**。

> **重要提示：** Secrets 必须是 Repository secrets，而不是 Environment secrets——除非 workflow 里明确声明了 `environment:`。如果 workflow 日志里 secrets 显示为空，这是最常见的原因。

**最小邮件部署所需 Secrets：**

| Secret | 作用 |
|--------|------|
| `LLM_API_KEY` | 主模型 API key |
| `LLM_MODEL` | 主模型名称 |
| `RESEND_API_KEY` | 邮件投递 |
| `EMAIL_TO` | 收件人地址 |

**推荐补充的 Secrets：**

| Secret | 作用 |
|--------|------|
| `LLM_BASE_URL` | 非 OpenAI 接口时的 base URL |
| `LLM_FILTER_API_KEY` | 筛选用的便宜模型 API key |
| `LLM_FILTER_BASE_URL` | 筛选模型的 base URL |
| `LLM_FILTER_MODEL` | 筛选模型名称 |
| `TAVILY_API_KEY` | 外部信号增强 |
| `SEMANTIC_SCHOLAR_API_KEY` | 更好的推荐质量 |

**完整反馈闭环所需 Secrets：**

| Secret | 作用 |
|--------|------|
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 账号 |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token |
| `D1_DATABASE_ID` | 存储反馈事件的 D1 数据库 |
| `FEEDBACK_ENDPOINT_BASE_URL` | 嵌入到反馈链接里的 Worker URL |
| `FEEDBACK_LINK_SIGNING_SECRET` | 签名 feedback token 的 HMAC 密钥 |

**可选 Variables**（Settings → Secrets and variables → Actions → Repository variables）：

| Variable | 默认值 | 作用 |
|----------|--------|------|
| `SEMANTIC_STATE_BACKEND` | `d1` | semantic state 后端（`d1` 或 `file`） |
| `SEMANTIC_MEMORY_ENABLED` | `true` | 是否启用 anti-repetition memory |
| `SEMANTIC_SEEN_TTL_DAYS` | `30` | 已看内容的抑制天数 |
| `SEMANTIC_MEMORY_MAX_IDS` | `5000` | memory store 最大条数 |
| `FEEDBACK_TOKEN_TTL_DAYS` | — | 签名 feedback 链接的有效期 |
| `FEEDBACK_REVIEWER` | — | 写入反馈事件的审阅者 ID |

### 远程 Semantic State

Workflows 不会把运行时状态写回 `main`，而是改为直接读写 D1：

- `daily-digest.yml` 会在运行前从 D1 导出 semantic state，运行后再把更新后的 `memory.json` 导回 D1
- `apply-feedback-queue.yml` 会在处理反馈前导出 seeds，处理后再把更新后的 `seeds.json` 导回 D1

这样 Git 历史保持干净，同时仍然保留本地 JSON 可检查、可编辑、可回传的操作方式。

### 首次部署清单

1. 把仓库推到 GitHub 并开启 Actions
2. 在 **Repository secrets** 下添加所有必需的 Secrets（注意不要放在 Environment 下）
3. 按需设置可选 Variables
4. 手动触发 **Daily Paper Digest**，`dry_run=true` — 检查日志和 artifacts
5. 用 `dry_run=false` 再跑一次 — 确认邮件送达，且 D1 semantic state 的导出/导回链路正常
6. *（仅完整反馈闭环）* 部署 Cloudflare Worker，确认 `apply-feedback-queue.yml` 跑通

### 成本估算

假设每天跑 1 次，原始候选约 40–60 条，进入 LLM 过滤约 10–25 条，最终 shortlist 约 6–10 条：

| 档位 | 模型分工 | 粗略月成本 |
|------|----------|-----------|
| 预算档 | DeepSeek（过滤）+ Gemini Flash（生成） | ~$2–8 |
| 平衡档 | DeepSeek（过滤）+ Claude Sonnet / Gemini Pro（生成） | ~$8–25 |
| 重度档 | 全程强模型，shortlist 更长，PDF 更多 | ~$20–50 |

主要成本在最终生成阶段，而该阶段只处理 shortlist。筛选阶段用便宜模型可以有效压低总花销。

## 其他说明

- `artifacts/` 和 `llm_filter_debug/` 是运行产物目录，可以安全删除。
- `state/semantic/` 是实时运行状态，除非打算重置，不要删除。
- 在 GitHub Actions 上，`memory.json` 和 `seeds.json` 存在 state branch 而不是 `main`。
- 如果 workflow 日志里 secrets 显示为空，最常见的原因是把 secrets 放在了 Environment 而非 Repository secrets 下。


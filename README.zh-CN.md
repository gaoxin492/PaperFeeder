# PaperFeeder（中文说明）

PaperFeeder 是一个**每日论文 + 博客摘要**流水线：用 **Semantic Scholar** 做个性化，并支持 **点赞/点踩反馈** 闭环。

> 英文版说明见 [README.md](README.md)。

---

## 项目是干什么的？

1. **定时/手动**拉 arXiv、博客等来源，经关键词与 LLM 筛选后生成 HTML 报告。  
2. 可通过 **Resend** 等发邮件；也可用 `--dry-run` 只生成本地 `report_preview.html`。  
3. 若配置了 Cloudflare Worker + D1，邮件/网页里可以对每篇论文 **👍 / 👎**，点击会记到 D1；之后用命令把结果**写回**本地的 `state/semantic/seeds.json`，影响后续推荐。

---

## 目录结构（一眼能看懂）

```text
PaperFeeder/
├── paperfeeder/          # 所有 Python 业务代码（主包）
├── scripts/              # 一键安装、反馈相关脚本
├── cloudflare/           # 反馈用 Worker + D1 表结构 SQL
├── state/semantic/       # 长期状态：种子 ID、最近见过的论文
├── artifacts/            # 每次运行生成的 manifest 等（可删，git 忽略）
├── user/                 # 你改的人设、关键词、提示词片段
├── tests/                # 单元测试
├── config.yaml           # 默认配置
└── main.py               # 跑摘要的主入口
```

### `paperfeeder/` 里重点文件

- 根目录几个**扁平模块**：`models.py`（论文/作者模型）、`email.py`（发信）、`chat.py`（调 LLM 的客户端）。  
- 主流程：`paperfeeder/pipeline/runner.py`。  
- 把反馈写进种子文件：`paperfeeder/cli/apply_feedback.py`（也可用 `python -m paperfeeder.cli.apply_feedback`）。

### `state/semantic/` 是什么？

| 文件 | 作用 |
|------|------|
| `seeds.json` | 长期保存：你标记过「喜欢 / 不喜欢」的 Semantic Scholar 论文 ID，用来影响后面推荐。 |
| `memory.json` | 短期记忆：最近出现过的论文键，减少同一篇反复刷脸。 |

这是**运行数据**，不是手写源码。

### `artifacts/` 是什么？

每次 digest 可能生成例如：

- `run_feedback_manifest_<run_id>.json`：这一期里每篇论文与反馈条目的对应关系。  
- `semantic_feedback_template_<run_id>.json`：给人填的问卷模板。

都是**生成物**，可删；已在 `.gitignore` 里忽略。

### `cloudflare/` 是什么？

- `feedback_worker.js`：部署在 Cloudflare 上的小服务，处理 `/feedback?t=...`（记录点赞）和 `/run?run_id=...`（看网页版报告）。  
- `d1_feedback_events.sql`：在 D1 里建表用的 SQL。

---

## 第一次怎么用？

### 1. 安装依赖

```bash
bash scripts/bootstrap.sh
source .venv/bin/activate
```

### 2. 配置密钥与账号

把 **`.env.example` 复制成 `.env`**，按里面注释填写（邮件、LLM、可选的反馈与 D1 等）。

这份 `.env` 主要用于**本地开发 / 本地测试**。如果你是用 GitHub Actions 部署远程定时任务，远程环境应当使用 GitHub 的 **Secrets / Variables**；workflow 不依赖仓库里的 `.env`。

还可以按需改：

- `config.yaml` 里的 `prompt_language`（决定报告 prompt 以中文还是英文为主）
- `user/research_interests.txt`（研究兴趣人设）  
- `user/keywords.txt`（想重点抓的关键词）
- `user/exclude_keywords.txt`（想过滤掉的噪音词）
- `user/arxiv_categories.txt`（想跟踪的 arXiv 分类）
- `user/prompt_addon.txt`（给 LLM 的附加说明）

现在推荐这样理解：`config.yaml` 是**主配置文件**；`user/blogs.yaml` 放博客源；`user/` 下面其他 txt 放你的研究画像文本。

如果别的使用者更习惯英文，可以把 `config.yaml` 里的 `prompt_language` 改成 `en-US`；默认是 `zh-CN`。

如果你想换一套起始画像，可以看 `user/examples/profiles/` 下面的预设模板：

- `frontier-ai-lab`
- `interpretability-alignment`
- `coding-agents-reasoning`
- `multimodal-generative`

你可以把里面的 txt 内容拷到 `user/` 根目录，或者直接在 `config.yaml` 里把路径指向某个 preset。

### 3. 跑一版摘要（先试跑，不发真邮件）

```bash
python main.py --dry-run
```

### 3b. 轻量调试（一篇假论文，不爬全网）

不想每次为了试功能都去拉几百篇、再过关键词/双阶段 LLM/Tavily？用 **`--debug-sample`**：从 JSON 读 1 篇（或几篇）固定数据，**跳过** arXiv/HF/S2 抓取、博客、粗筛/精筛 LLM、Tavily 增强；仍会走 **写报告 → manifest → 邮件/HTML 预览 →（若配置了）D1** 这条链，适合验证反馈链接、Worker、排版等。

1. （可选）复制模板：  
   `cp tests/debug_sample.example.json tests/debug_sample.json`  
2. 编辑 `tests/debug_sample.json`：改 `title`、`url`、`arxiv_id`；若不复制，默认会用仓库里的 `tests/debug_sample.example.json`。若要测 👍/👎 签名链接，填上能解析的 **`semantic_paper_id`**（或配好 `SEMANTIC_SCHOLAR_API_KEY` 让程序解析）。

```bash
# 默认：**不调**主报告 LLM，只用固定极简 HTML（测邮件 / manifest / D1 / Worker，省 token）
python main.py --debug-sample --dry-run

# 同上但**真发邮件**（需配置 RESEND 等）
python main.py --debug-sample

# 调试样本仍用 JSON，但**要**主报告 LLM 写正文时加上：
python main.py --debug-sample --debug-llm-report --dry-run

# 正常抓取论文，但报告正文仍用极简 HTML（不调主 digest LLM）
python main.py --debug-minimal-report --dry-run

# 指定别的 JSON
python main.py --debug-sample --debug-sample-path path/to/papers.json --dry-run
```

默认 **不会** 更新 `state/semantic/memory.json`（避免调试把记忆弄脏）；若要更新，加上 **`--debug-write-memory`**。

`python main.py --dry-run` 会在本地写出 `report_preview.html`，也可能在 `artifacts/` 里生成 manifest 等文件。

### 4. 正式跑（例如看最近 3 天）

```bash
python main.py --days 3
```

（是否真发邮件取决于你是否关掉 dry-run 以及 `.env` 里邮件配置。）

---

## 常用命令速查

| 你想做的事 | 命令 |
|------------|------|
| 本地试跑、生成预览 | `python main.py --dry-run` |
| 指定回溯天数 | `python main.py --days 3` |
| 把「已审核的反馈」合并进 seeds（先演练） | `python -m paperfeeder.cli.apply_feedback --manifest-file artifacts/run_feedback_manifest_<run_id>.json --dry-run` |
| 同上，真正写入 `seeds.json` | 去掉 `--dry-run` |
| 从 **Cloudflare D1** 拉待处理反馈再应用（先演练） | `python -m paperfeeder.cli.apply_feedback --from-d1 --manifest-file artifacts/run_feedback_manifest_<run_id>.json --manifests-dir artifacts --dry-run` |

脚本包装（等价于上面 apply_feedback）：

```bash
python scripts/semantic_feedback_apply.py --manifest-file artifacts/run_feedback_manifest_<run_id>.json --dry-run
```

---

## 配置优先级（谁覆盖谁）

程序会按顺序合并，**后面的覆盖前面的**：

1. `config.yaml`  
2. `user/blogs.yaml`  
3. **环境变量**（`.env` 里由 `python-dotenv` 加载的也算）  
4. `user/research_interests.txt`、`user/prompt_addon.txt`、`user/keywords.txt`、`user/exclude_keywords.txt`、`user/arxiv_categories.txt`

现在正常使用时，建议把 `config.yaml` 当成**主配置文件**，把博客源写在 `user/blogs.yaml`，再配合修改 `user/` 目录和 `.env`。

其中这几个列表文件都支持“**每行一个条目**”的格式：

- 空行会忽略
- 以 `#` 开头的行会忽略
- 行内 `#` 后面的注释也会忽略

与语义状态相关的默认路径在 `config.yaml` 里一般是：

```yaml
semantic_scholar_seeds_path: "state/semantic/seeds.json"
semantic_memory_path: "state/semantic/memory.json"
```

---

## Memory（到底是什么）

先把 `memory` 和 `feedback` 分开理解，否则很容易混。

### `memory.json` 做什么

`state/semantic/memory.json` 只负责一件事：

1. 记住最近已经看过哪些论文
2. 下次跑 digest 时尽量不要重复推给你

它不是偏好学习，不是打分器，也不会改 LLM 的“口味”。它本质上是**去重 / 降重缓存**。

### `seeds.json` 做什么

`state/semantic/seeds.json` 负责另一件事：

1. 记录你明确喜欢的 Semantic Scholar 论文 ID
2. 记录你明确不喜欢的 Semantic Scholar 论文 ID
3. 把这些正负样本喂给 Semantic Scholar recommendation API

所以：

1. `memory.json` 解决“别老给我看同一篇”
2. `seeds.json` 解决“以后多给我推这种 / 少给我推这种”

### 这两者怎么影响每天的 digest

每天跑 `main.py` 时：

1. arXiv、博客、手动源照常抓
2. 如果开了 `semantic_scholar_enabled`，会额外根据 `seeds.json` 去请求推荐论文
3. `memory.json` 会把最近见过的内容压掉，减少重复

关键点：

1. `memory.json` 不会微调 LLM
2. `seeds.json` 也不会微调 LLM
3. 它们影响的是**候选论文集合**，不是模型参数

### 你平时什么时候会碰到它们

本地手动跑时：

1. `memory.json` 会在跑完后更新“今天见过哪些论文”
2. `seeds.json` 只有在你应用反馈后才会改

如果你完全不做 feedback：

1. `memory.json` 还是有用
2. `seeds.json` 可能一直是空的

---

## Feedback（到底是什么）

`feedback` 是一条单独的闭环，它的目标不是去重，而是把你的显式偏好写回 `seeds.json`。

### 整条反馈链路

1. `python main.py` 生成 digest
2. 运行时会产出 manifest / template 到 `artifacts/`
3. 邮件或网页里的 👍 / 👎 链接会打到你部署的 Cloudflare Worker
4. Worker 把事件写进 D1
5. `apply_feedback` 再把这些事件转换成 `seeds.json` 里的正负样本

所以 feedback 不是“当场改变今天的报告”，而是：

1. 先记录反馈
2. 再在后续运行里影响推荐候选

### 最关键的几个配置

复制 **`.env.example` → `.env`** 后，至少关注这些：

| 要配什么 | 填在哪 | 作用 |
|----------|--------|------|
| Worker 地址 | `.env` → `FEEDBACK_ENDPOINT_BASE_URL` | 邮件里 👍 / 👎 链接打到哪里 |
| 签名密钥 | `.env` + Worker secret → `FEEDBACK_LINK_SIGNING_SECRET` | 保证反馈链接不会被伪造 |
| D1 访问 | `.env` → `CLOUDFLARE_ACCOUNT_ID`、`CLOUDFLARE_API_TOKEN`、`D1_DATABASE_ID` | 让 Python 程序上传 digest、拉取反馈 |
| Semantic Scholar API | `.env` → `SEMANTIC_SCHOLAR_API_KEY` | 提高 `semantic_paper_id` 解析成功率，否则很多条目没有按钮 |
| 邮件附件模式 | `.env` → `FEEDBACK_EMAIL_ATTACHMENTS` | 控制是否把 manifest / template 挂到邮件里 |

### Worker 最短部署步骤

```bash
cd cloudflare
cp wrangler.toml.example wrangler.toml
# 编辑 wrangler.toml：把 database_id 换成 `wrangler d1 create paperfeeder-feedback` 输出里的 ID
npx wrangler d1 execute paperfeeder-feedback --remote --file=d1_feedback_events.sql
npx wrangler secret put FEEDBACK_LINK_SIGNING_SECRET
npx wrangler deploy
```

部署后，把 Worker URL 写进 `.env`：

```bash
FEEDBACK_ENDPOINT_BASE_URL=https://你的-worker.workers.dev
```

### Web Viewer 是什么

`Open Feedback Web Viewer` 只是一个网页入口：

1. 方便你在浏览器里看整份 digest
2. 方便分享或补点反馈

它不是反馈本身。每篇旁边的 👍 / 👎 才是核心链路。

如果不要这块入口，可以在 `.env` 里设：

```bash
FEEDBACK_WEB_VIEWER_LINK_IN_EMAIL=false
```

---

## GitHub Actions（远程每天定时发送）

这一章最重要，因为它决定你是不是能把 PaperFeeder 变成**远程定时发送服务**。

仓库里有两个关键 workflow：

| Workflow | 作用 |
|----------|------|
| `.github/workflows/daily-digest.yml` | 每天定时跑 digest，发邮件，并把最新 `memory.json` 持久化到 state 分支 |
| `.github/workflows/apply-feedback-queue.yml` | 定时把 D1 里的 pending 反馈合并进 `seeds.json` |

### 它们各自怎么工作

#### 1. `daily-digest.yml`

默认行为：

1. 每天 `00:01 UTC` 运行一次，也就是北京时间 `08:01`
2. 从 state 分支读取 `state/semantic/memory.json` 和 `state/semantic/seeds.json`
3. 运行 `python main.py`
4. 如果不是 dry run，就把更新后的 `memory.json` 推回 state 分支

这条 workflow 负责：

1. 远程定时发送邮件
2. 维持“最近看过什么”的远程记忆

#### 2. `apply-feedback-queue.yml`

默认行为：

1. 默认每 3 天在北京时间 `00:30` 跑一次，对应 UTC cron 是 `30 16 */3 * *`
2. 从 state 分支读取 `seeds.json`
3. 从 D1 拉 pending feedback
4. 执行 `python -m paperfeeder.cli.apply_feedback --from-d1`
5. 把更新后的 `seeds.json` 推回 state 分支

这条 workflow 负责：

1. 让远程收集到的 👍 / 👎 真正转化成推荐偏好

### 什么是 state 分支

workflow 不会把运行时状态直接写回 `main`，而是写到一个单独分支：

1. 默认叫 `memory-state`
2. 也可以用仓库变量 `SEED_STATE_BRANCH` 改名

这个分支只存：

1. `state/semantic/memory.json`
2. `state/semantic/seeds.json`

这样做的好处是：

1. 代码分支保持干净
2. 运行时状态长期保存
3. GitHub Actions 每次跑都能接着上次的状态继续

### 远程定时发送最小部署步骤

如果你的目标是“每天自动跑并发邮件”，按这个顺序来：

#### 第 1 步：把仓库放到 GitHub

1. 推到自己的 GitHub 仓库
2. 打开 Actions 权限

#### 第 2 步：准备邮件和模型 secrets

这里可以把它理解成：**本地运行看 `.env`，GitHub Actions 运行看 Secrets / Variables**。两套用途分开，不需要把本地 `.env` 提交到仓库。

至少要在 GitHub 仓库 `Settings -> Secrets and variables -> Actions -> Secrets` 里配置：

1. `LLM_API_KEY`
2. `LLM_BASE_URL`（若你不是默认 OpenAI-compatible 地址）
3. `LLM_MODEL`
4. `RESEND_API_KEY`
5. `EMAIL_TO`

如果你还要更完整功能，再配：

1. `LLM_FILTER_API_KEY`
2. `LLM_FILTER_BASE_URL`
3. `LLM_FILTER_MODEL`
4. `TAVILY_API_KEY`
5. `SEMANTIC_SCHOLAR_API_KEY`
6. `CLOUDFLARE_ACCOUNT_ID`
7. `CLOUDFLARE_API_TOKEN`
8. `D1_DATABASE_ID`
9. `FEEDBACK_ENDPOINT_BASE_URL`
10. `FEEDBACK_LINK_SIGNING_SECRET`

#### 第 3 步：准备 Actions variables

在 `Settings -> Secrets and variables -> Actions -> Variables` 里建议设置：

1. `SEED_STATE_BRANCH`
   默认可不填，程序会用 `memory-state`
2. `SEMANTIC_MEMORY_ENABLED`
3. `SEMANTIC_SEEN_TTL_DAYS`
4. `SEMANTIC_MEMORY_MAX_IDS`
5. `FEEDBACK_TOKEN_TTL_DAYS`
6. `FEEDBACK_REVIEWER`

#### 第 4 步：首次手动跑一次 Daily Digest

在 GitHub Actions 页面手动触发：

1. 选择 `Daily Paper Digest`
2. 先用 `dry_run=true` 验证
3. 确认报告、artifact、日志正常后，再跑一次 `dry_run=false`

第一次非 dry run 后：

1. 如果 state 分支不存在，workflow 会自己初始化
2. 后面每天会在这个分支上持续更新 `memory.json`

#### 第 5 步：确认定时任务

当前默认 cron：

1. `daily-digest.yml`：`1 0 * * *`
2. `apply-feedback-queue.yml`：`30 16 */3 * *`

它们都是 **UTC**。

如果你要改成自己的时区，就直接改 workflow 里的 cron。

按你现在这套北京时间配置来理解就是：

1. `daily-digest.yml` 会在北京时间每天 `08:01` 发送
2. `apply-feedback-queue.yml` 会在北京时间每 3 天凌晨 `00:30` 同步一次反馈

### 远程每天发送时，系统每天会发生什么

每天的链路可以概括成：

1. GitHub Actions 定时触发 `daily-digest.yml`
2. workflow 从 state 分支恢复昨天的 `memory.json` / `seeds.json`
3. 跑 `main.py`
4. 发送邮件
5. 把新的 `memory.json` 推回 state 分支

如果用户点了 👍 / 👎：

1. 反馈先落到 D1
2. `apply-feedback-queue.yml` 定时拉取这些事件
3. 写回 `seeds.json`
4. 之后的推荐候选开始变化

### 最小远程部署建议

如果你只想先实现“每天自动发邮件”，其实只需要：

1. 配好 `LLM_*`
2. 配好 `RESEND_API_KEY`
3. 配好 `EMAIL_TO`
4. 启用 `daily-digest.yml`

这时：

1. 能定时生成 digest
2. 能定时发邮件
3. `memory.json` 也能持续累积

但还没有 feedback 闭环。

如果你要 feedback 闭环，再额外加：

1. Cloudflare Worker
2. D1
3. `apply-feedback-queue.yml`

---

## 运行测试

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 其他说明

- `artifacts/`、`llm_filter_debug/` 是运行产物目录，默认被 git 忽略。  
- 若使用 GitHub Actions，会在 **state 分支**上读写 `state/semantic/seeds.json` 和 `memory.json`；说明见上文 **「GitHub Actions、`seeds.json` 和记忆」**。

---

## 和英文 README 的关系

- **中文**：本文档 `README.zh-CN.md`，面向阅读与操作说明。  
- **英文**：[README.md](README.md)，内容与结构保持一致，便于国际协作或 CI 引用。

如有某一段仍看不懂，可以只问那一块（例如「只配邮件、不配 Worker」的最小配置）。

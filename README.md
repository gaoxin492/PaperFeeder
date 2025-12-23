# PaperFeeder — Daily Paper Assistant

PaperFeeder 自动从 arXiv、HuggingFace Daily Papers 和手动列表抓取论文，使用关键词与 LLM 进行粗筛与精筛，汇总成每日报告并通过邮件发送。适合研究者自动化跟踪感兴趣方向的新进展。

- 语言：Python 3.10+
- 目标：自动化抓取、筛选、基于 LLM 的评分与汇报生成

主要功能
- 从 `arXiv` 与 `HuggingFace Daily Papers` 拉取论文
- 基于关键词的快速召回（title + abstract）
- 基于 LLM 的粗筛（Coarse Filter）与精筛（Fine Filter）
- 使用外部研究 API（Tavily）收集社区信号（可选）
- 生成 HTML 报告并通过 Resend 发邮件（或保存为文件用于调试）

快速开始
1. 克隆并进入仓库

```bash
git clone <repo-url>
cd PaperFeeder
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 准备环境变量
- 复制 `.env.example`（若存在）或在项目根目录创建 `.env`，填入你的 API keys：

```
LLM_API_KEY=...
LLM_FILTER_API_KEY=...
TAVILY_API_KEY=...
RESEND_API_KEY=...
EMAIL_TO=you@example.com
```

3. 配置 `config.yaml`
- 复制 `config.example.yaml` 为 `config.yaml` 并根据需要调整关键词、类别与参数（如 `max_papers`、`llm_filter_enabled` 等）。

运行
- 本地 dry-run（不发邮件，仅生成并保存报告）：

```bash
python main.py --dry-run
```

- 正式运行（会发送邮件）：

```bash
python main.py
```

配置说明（重要字段）
- `LLM_API_KEY` / `LLM_FILTER_API_KEY`：用于摘要与筛选的 LLM API Key（支持 OpenAI/Anthropic 等兼容后端）。
- `TAVILY_API_KEY`：可选，若提供将使用 Tavily 的研究 API 获取社区信号（没有则降级为 mock researcher）。
- `RESEND_API_KEY`：用于通过 Resend 发送邮件。
- `EMAIL_TO`：接收报告的邮箱地址。
- `config.yaml`：包含关键词、arXiv 分类、去重/数量上限、是否启用 LLM 过滤等可调参数。

排查问题
- 看不到 `TAVILY_API_KEY`：确认 `.env` 放在运行目录且 `TAVILY_API_KEY=...` 已设置；`config.py` 会自动加载 `.env` 并把该值注入 `Config`。
- 报告包含旧论文：arXiv 使用 `published` 字段做过滤，HuggingFace 源可能不做截断，若见到历史论文，请检查 `config.days` 或在 `sources.py` 中添加日期过滤。
- 网络超时 / arXiv 慢：arXiv 查询可能较慢，脚本里有重试与超时策略；必要时增大 `ClientTimeout` 或降低 `max_results`。

开发与贡献
- 代码风格：尽量保持清晰、类型注解与早期返回（guard clauses）。
- 添加新数据源或研究 API 请在 `sources.py` / `researcher.py` 中新增类并遵循 `BaseSource` / `PaperResearcher` 接口。

许可证
- 请在此处填写你的许可证信息（例如 MIT）。

更多帮助
- 阅读 `DEPLOY.md` 获取 GitHub Actions / 部署指南，或打开 issue 说明你的问题与日志片段。

# 📚 Daily Paper Assistant

一个自动化的科研论文追踪助手，每天自动搜集、筛选、总结最新论文并发送到你的邮箱。

## ✨ 功能特性

- **多来源聚合**: arXiv、HuggingFace Daily Papers、手动添加
- **智能筛选**: 关键词匹配 + 可选 LLM 精筛
- **AI 总结**: Claude 生成论文摘要和研究洞察
- **自动推送**: 通过 GitHub Actions 定时发送邮件
- **可扩展**: 预留了作者筛选、单位筛选、Embedding 相似度等接口

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/yourusername/paper-assistant.git
cd paper-assistant
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml，设置你的关键词和研究兴趣
```

### 4. 设置环境变量

```bash
export ANTHROPIC_API_KEY="your-api-key"
export RESEND_API_KEY="your-resend-key"
export EMAIL_TO="your-email@example.com"
```

### 5. 本地测试

```bash
# 预览模式（不发送邮件）
python main.py --dry-run

# 正常运行
python main.py

# 查看更多天的论文
python main.py --days 3
```

## 📧 部署到 GitHub Actions

1. Fork 这个仓库
2. 在仓库设置中添加 Secrets:
   - `ANTHROPIC_API_KEY`
   - `RESEND_API_KEY`
   - `EMAIL_TO`
3. 启用 GitHub Actions
4. 默认每天 UTC 7:00 运行（可在 `.github/workflows/daily-digest.yml` 中修改）

## 📁 项目结构

```
paper-assistant/
├── main.py              # 主入口
├── config.py            # 配置管理
├── models.py            # 数据模型
├── sources.py           # 论文来源（arXiv, HF, Manual）
├── filters.py           # 筛选器（关键词, LLM, 作者）
├── summarizer.py        # Claude 摘要生成
├── emailer.py           # 邮件发送
├── config.yaml          # 配置文件
├── manual_papers.json   # 手动添加的论文
└── .github/workflows/   # GitHub Actions
```

## 🔧 配置说明

### 关键词配置

```yaml
keywords:
  - diffusion model
  - chain of thought
  - ai safety
```

论文标题或摘要匹配任一关键词即被选中。

### 研究兴趣描述

用于 LLM 筛选和生成更相关的总结：

```yaml
research_interests: |
  我的研究方向包括：
  1. 扩散模型，特别是语言扩散模型
  2. LLM 推理，包括 Chain-of-Thought
  ...
```

### LLM 筛选（可选）

当论文太多时，可启用 LLM 二次筛选：

```yaml
llm_filter_enabled: true
llm_filter_threshold: 30  # 超过30篇时启用
```

## 📝 手动添加论文

编辑 `manual_papers.json`：

```json
{
  "papers": [
    {
      "url": "https://arxiv.org/abs/2401.00001",
      "notes": "导师推荐"
    }
  ]
}
```

也可以只添加 URL，系统会自动获取元数据。

## 🔮 未来计划

- [ ] Cloudflare D1 集成（支持 Chatbot 自动添加论文）
- [ ] Telegram Bot 交互
- [ ] Embedding 相似度筛选
- [ ] 作者/单位关注列表
- [ ] OpenReview 会议论文追踪
- [ ] 论文阅读进度追踪

## 📄 License

MIT

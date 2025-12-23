# 部署指南（GitHub Actions / 本地测试）

本文档介绍如何把 PaperFeeder 部署到 GitHub Actions、在本地测试以及常见故障排查要点。适合希望每天自动生成并发送论文简报的研究者或团队。

1) 必备 API Keys（在仓库 Secrets 或本地 .env 中设置）
- `LLM_API_KEY` 或 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`：主 LLM 用于摘要/合成（可选替代项）。
- `LLM_FILTER_API_KEY`（可选）：用于更廉价的筛选模型（filter 阶段）。
- `TAVILY_API_KEY`（可选）：用于获取社区信号的研究 API（没有则使用本地 mock researcher）。
- `RESEND_API_KEY`：Resend 邮件服务 API key，用于发送报告。
- `EMAIL_TO`：报告接收人邮箱地址。

2) 在 GitHub 上创建仓库并推送

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/paperfeeder.git
git branch -M main
git push -u origin main
```

3) 配置 GitHub Actions Secrets
- 打开仓库 → Settings → Secrets and variables → Actions → New repository secret
- 添加上面列出的 keys（键名全大写，如 `TAVILY_API_KEY`）。确保 `EMAIL_TO` 为正确的接收邮箱。

4) 工作流与触发
- 仓库可包含 `.github/workflows/daily-digest.yml`（示例已包含）。默认可按 schedule 定期触发，也可手动运行：
  - Actions → Daily Paper Digest → Run workflow → 填写 `days_back` 或勾选 `dry_run`
- 若需更改触发时间，调整 workflow 中的 `cron` 表达式。

5) 本地开发与测试（推荐先做）

- 安装依赖并创建虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- 在项目根创建 `.env` 并填写 keys，或直接在 CI secrets 中设置（注意本地测试需要 .env）：

```
LLM_API_KEY=...
LLM_FILTER_API_KEY=...
TAVILY_API_KEY=...
RESEND_API_KEY=...
EMAIL_TO=you@example.com
```

- 运行 dry-run（不会发送邮件，只会保存报告到 `report_preview.html`）：

```bash
python main.py --dry-run
```

6) 常见问题与排查
- 启动时报 `TAVILY_API_KEY not found`：
  - 确认 `.env` 在运行目录且包含 `TAVILY_API_KEY=...`，或者在 GitHub Secrets 中正确设置。`config.py` 会自动加载 `.env`（通过 `load_dotenv()`）。
- 报告包含旧论文：
  - arXiv 在 `sources.py` 中使用 `published` 字段做过滤，但 HuggingFace 源可能没有严格日期截断。可通过运行时参数 `--days` 调整回溯天数，或在 `sources.py` 为 HuggingFace 加入日期过滤。
- arXiv 响应慢或超时：
  - arXiv 查询可能需要 10–60s，脚本内有重试与较长的超时限制。可减少 `max_results` 或增加超时。
- 邮件未收到：
  - 在 Actions 日志中查看 `emailer` 相关输出；确认 `RESEND_API_KEY` 与 `EMAIL_TO` 设置正确并检查垃圾箱；可先使用 `--dry-run` 保存 HTML，确认内容正常。

7) 可选改进与扩展
- 更严格的日期过滤：在 `HuggingFaceSource.fetch()` 中对 `publishedAt` 做 cutoff（与 `ArxivSource` 一致）。
- 添加新数据源：在 `sources.py` 新增 `BaseSource` 子类并在 `main.fetch_papers()` 注册。
- 集成更多研究 API：在 `researcher.py` 中实现 `PaperResearcher`（例如替换或扩展 Tavily）。

如果你希望，我可以：
- 生成或更新 `.github/workflows/daily-digest.yml` 的示例 workflow；
- 在日志中增加启动时的密钥存在检测（只打印是否存在，不泄露密钥）。



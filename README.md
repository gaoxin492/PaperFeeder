# 📚 PaperFeeder

> **AI Agent for Daily Paper & Blog Digest**  
> Hunt for "The Next Big Thing", despise incremental work.

An intelligent content recommendation system that automatically fetches, filters, researches, and summarizes academic papers from arXiv/HuggingFace **AND blog posts from top AI labs** (OpenAI, Anthropic, DeepMind, etc.). Powered by LLM agents and community signal enrichment.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

📌 **Recent updates:**
- Semantic Scholar personalization is now production-ready (seed profile + anti-repetition memory + web feedback loop).
- Feedback flow is now digest-notification + web viewer actions (manual apply gate preserved).
- Full changelog: [UPDATE.md](UPDATE.md)

---

## ✨ Key Features

### 🤖 **AI Agent Workflow**
Seven-stage intelligent pipeline that mimics how a senior researcher screens content:

```
Fetch Papers → Fetch Blogs → Keyword Filter → LLM Coarse Filter → Research → LLM Fine Filter → Synthesis
   (arXiv/HF)    (RSS Feeds)   (Cast Wide Net)   (Quick Score)    (Signals)  (Deep Ranking)    (Report)
```

### 📝 **NEW: Blog Integration**
- **Priority Sources**: OpenAI, Anthropic, DeepMind, Google AI, Meta AI, BAIR, Karpathy, Lilian Weng, etc.
- **Smart Filtering**: Not all blogs are worth reading! LLM filters out marketing fluff and off-topic posts
- **Deep Analysis**: Top 1-3 blogs get full analysis with Key Insights and Action Items
- **RSS/Atom Support**: Easy to add custom blogs via `config.yaml`

### 🔍 **Community Signal Enrichment**
- Uses **Tavily API** to search GitHub, Reddit, Twitter, HuggingFace
- Extracts: GitHub stars, community discussions, reproducibility issues
- Integrates external validation into paper evaluation

### 🎯 **Two-Stage LLM Filtering**
- **Stage 1 (Coarse)**: Fast screening based on title + abstract → Top 20
- **Stage 2 (Fine)**: Deep ranking with community signals → Top 1-5

### 📰 **"Editor's Choice" Style Reports**
- Senior Principal Researcher persona (OpenAI/DeepMind/Anthropic caliber)
- 犀利点评，中英文夹杂 (Sharp commentary, bilingual)
- Sections: 📢 Blog Highlights, 🏆 Editor's Choice, 🔬 Deep Dive, 🌀 Signals & Noise

### 🔧 **Flexible & Extensible**
- Supports any OpenAI-compatible LLM (OpenAI, Claude, Gemini, DeepSeek, Qwen, local models)
- PDF multimodal input for deep analysis (Claude, Gemini)
- Customizable research interests and filtering criteria

### 🧠 **Semantic Scholar Personalization**
- Seed-based recommendations (`positive_paper_ids` / `negative_paper_ids`)
- Anti-repetition memory (`semantic_scholar_memory.json`) with TTL
- Human preference loop via web viewer (`positive` / `negative` / `undecided-reset`) + manual apply

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- API Keys:
  - **Required**: LLM API key (OpenAI, Claude, etc.)
  - **Optional**: Tavily API key (for community research), Resend API key (for email)

### Installation

```bash
# Clone the repository
git clone https://github.com/gaoxin492/PaperFeeder.git
cd PaperFeeder

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys
```

### Configuration

Create a `.env` file:

```bash
# LLM Settings (Main - for summarization)
LLM_API_KEY=sk-xxxxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# LLM Settings (Filter - for two-stage filtering)
LLM_FILTER_API_KEY=sk-xxxxx  # Can use cheaper model
LLM_FILTER_BASE_URL=https://api.openai.com/v1
LLM_FILTER_MODEL=gpt-4o-mini

# Research & Enrichment (Optional)
TAVILY_API_KEY=tvly-xxxxx  # Get from https://tavily.com

# Email Delivery (Optional)
RESEND_API_KEY=re-xxxxx
EMAIL_FROM=papers@resend.dev
EMAIL_TO=your@email.com
```

### Run Locally

```bash
# Dry run (save report to HTML file)
python main.py --dry-run

# Send via email
python main.py

# Fetch last 3 days of papers, 7 days of blogs
python main.py --days 3 --blog-days 7

# Disable blog fetching
python main.py --no-blogs
```

### 📧 Automated Daily Delivery

**Want daily paper digests delivered to your inbox automatically?**

Use **GitHub Actions** for **FREE** automated deployment (no server needed):

1. Fork this repository
2. Add your API keys as GitHub Secrets
3. Enable GitHub Actions
4. Receive daily emails at 8 AM (configurable)

**👉 See [DEPLOY.md](DEPLOY.md) for complete setup guide** (takes ~5 minutes)

✨ **Recommended**: Start with `--dry-run` locally to test your configuration, then deploy to GitHub Actions for daily automation!

---

## 🧠 Semantic Scholar Personalization

This is the main personalization feature in PaperFeeder:
- seed profile controls recommendation direction
- memory avoids repeated recommendations
- web feedback updates preferences (via manual apply)

### 1) Seed + Memory Setup

Configure `config.yaml`:

```yaml
semantic_scholar_enabled: true
semantic_scholar_max_results: 30
semantic_scholar_seeds_path: "semantic_scholar_seeds.json"
semantic_memory_enabled: true
semantic_memory_path: "semantic_scholar_memory.json"
semantic_seen_ttl_days: 30
semantic_memory_max_ids: 5000
```

Create `semantic_scholar_seeds.json`:

```json
{
  "positive_paper_ids": ["CorpusId:282913080", "CorpusId:270562552"],
  "negative_paper_ids": ["CorpusId:283933653"]
}
```

Notes:
- Numeric IDs are auto-normalized to `CorpusId:<id>`.
- `positive_paper_ids` = "more like this", `negative_paper_ids` = "avoid this direction".

### 2) Preference Feedback Flow (Current)

1. Run `Daily Paper Digest`.
2. Open digest email.
3. Click run-level web viewer link.
4. Click `positive` / `negative` / `undecided` in viewer.
5. Run `Apply Feedback Queue`:
   - `dry_run=true` first
   - then `dry_run=false` to persist seeds.

Notes:
- During digest export, report-visible ArXiv/HuggingFace papers now use best-effort Semantic Scholar ID resolution (existing ID -> arXiv mapping -> conservative title match).
- If resolution fails (rate limit/network/budget), papers remain visible but non-actionable (no per-paper action links).
- Seed updates still require the apply step; clicking feedback alone does not persist seed changes until apply runs.

Required keys (GitHub Secrets / `.env`):

```bash
FEEDBACK_ENDPOINT_BASE_URL=https://paperfeeder-feedback.<subdomain>.workers.dev
FEEDBACK_LINK_SIGNING_SECRET=<shared-secret>
FEEDBACK_TOKEN_TTL_DAYS=7
FEEDBACK_REVIEWER=<optional reviewer override>

CLOUDFLARE_ACCOUNT_ID=<account-id>
CLOUDFLARE_API_TOKEN=<api-token>
D1_DATABASE_ID=<database-id>
```

Feedback semantics:
- `positive`: add to positive seeds and remove from negative.
- `negative`: add to negative seeds and remove from positive.
- `undecided`: reset state by removing from both seed lists.

### 3) State Branch Model (Recommended)

- Default: if `SEED_STATE_BRANCH` is unset, workflows use `memory-state`.
- Seeds + memory are loaded from state branch before run.
- Apply writes seeds back to state branch.
- Digest writes memory back to state branch.

### 4) What You Actually Need Daily

- Needed daily: `Daily Paper Digest` + `Apply Feedback Queue` workflows.
- Optional/local debug: `scripts/apply_semantic_feedback_queue.sh`.

Details:
- Personalization operations: [PERSONALIZATION_AND_MEMORY.md](docs/PERSONALIZATION_AND_MEMORY.md)
- Cloudflare + D1 manual setup: [FEEDBACK_INFRA_SETUP.md](docs/FEEDBACK_INFRA_SETUP.md)

---

## 🏗️ Architecture

### AI Agent Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ Stage 1a: FETCH PAPERS (Recall)                             │
│ • arXiv (cs.LG, cs.CL, cs.CV, etc.)                         │
│ • HuggingFace Daily Papers                                   │
│ • Manual additions                                           │
└────────────────────┬────────────────────────────────────────┘
                     │ ~50-100 papers
┌────────────────────┴────────────────────────────────────────┐
│ Stage 1b: FETCH BLOGS (NEW!)                                │
│ • Priority: OpenAI, Anthropic, DeepMind, Google AI, Meta AI │
│ • Researchers: Karpathy, Lilian Weng, Chris Olah            │
│ • Academic: BAIR, Stanford HAI, Distill.pub                 │
│ • Custom RSS feeds via config.yaml                          │
└────────────────────┬────────────────────────────────────────┘
                     │ ~10-20 blog posts
┌────────────────────▼────────────────────────────────────────┐
│ Stage 2: KEYWORD FILTER (Cast Wide Net)                     │
│ • Match keywords in title + abstract (papers only)          │
│ • Exclude noise (medical, hardware, etc.)                   │
│ • Strategy: 宁可错杀，不可漏过                              │
└────────────────────┬────────────────────────────────────────┘
                     │ ~30-50 papers
┌────────────────────▼────────────────────────────────────────┐
│ Stage 3: LLM COARSE FILTER (Quick Score)                    │
│ • Input: Title + Abstract + Authors                         │
│ • Criteria: Relevance, Novelty, Clarity                     │
│ • Output: Scores (0-10), Top 20 candidates                  │
└────────────────────┬────────────────────────────────────────┘
                     │ ~20 papers
┌────────────────────▼────────────────────────────────────────┐
│ Stage 4: RESEARCH & ENRICHMENT (Community Signals)          │
│ • Tavily search: GitHub, Reddit, Twitter, HuggingFace       │
│ • Extract: Stars, discussions, reproducibility              │
│ • Store in paper.research_notes                             │
└────────────────────┬────────────────────────────────────────┘
                     │ 20 papers (enriched)
┌────────────────────▼────────────────────────────────────────┐
│ Stage 5: LLM FINE FILTER (Deep Ranking)                     │
│ • Input: Title + Abstract + Authors + Community Signals     │
│ • Criteria: Surprise, Significance, External Validation     │
│ • Output: Top 3-5 papers with detailed reasons              │
└────────────────────┬────────────────────────────────────────┘
                     │ 3-5 papers + blog posts
┌────────────────────▼────────────────────────────────────────┐
│ Stage 6: SYNTHESIS (Report Generation)                      │
│ • Senior Principal Researcher persona                       │
│ • Blog filtering: Select Top 1-3 valuable posts             │
│ • PDF multimodal input (if supported)                       │
│ • Output: HTML report with MathJax support                  │
└─────────────────────────────────────────────────────────────┘
```

### Module Overview

```
PaperFeeder/
├── main.py              # AI Agent orchestration
├── sources.py           # Paper fetchers (arXiv, HuggingFace, Manual)
├── blog_source.py       # Blog fetchers via RSS/Atom (NEW!)
├── filters.py           # Two-stage LLM filtering
├── researcher.py        # Tavily-powered community research
├── summarizer.py        # Report generation with blog & paper analysis
├── llm_client.py        # Universal LLM client (OpenAI-compatible)
├── emailer.py           # Email delivery (Resend, SendGrid, File)
├── models.py            # Data models (Paper, Author, etc.)
├── config.py            # Configuration management
└── config.yaml          # User configuration
```

---

## 📖 Usage Guide

### Configure Blog Sources

Edit `config.yaml`:

```yaml
# Enable/disable blog fetching
blogs_enabled: true
blog_days_back: 7  # How many days back to look

# Which blogs to enable (if not specified, uses all priority blogs)
enabled_blogs:
  # === Top AI Labs (Priority - filtered for research value) ===
  - openai          # OpenAI Blog
  - anthropic       # Anthropic Blog
  - deepmind        # Google DeepMind
  - google_ai       # Google AI Blog
  - meta_ai         # Meta AI Blog
  
  # === Academic Labs ===
  - bair            # Berkeley AI Research
  
  # === Individual Researchers ===
  - karpathy        # Andrej Karpathy
  - lilianweng      # Lil'Log (Lilian Weng @ OpenAI)
  - colah           # Chris Olah
  - distill         # Distill.pub

# Add your own custom blogs
custom_blogs:
  my_favorite_blog:
    name: "My Favorite AI Blog"
    feed_url: "https://example.com/feed.xml"
    website: "https://example.com/blog"
    priority: true  # true = gets deep analysis
```

### Pre-configured Blog Sources

| Source | RSS Feed | Type |
|--------|----------|------|
| OpenAI | `openai.com/news/rss.xml` | AI Lab |
| Anthropic | `anthropic.com/rss.xml` | AI Lab |
| DeepMind | `deepmind.google/blog/rss.xml` | AI Lab |
| Google AI | `blog.google/technology/ai/rss/` | AI Lab |
| Meta AI | `ai.meta.com/blog/rss/` | AI Lab |
| BAIR | `bair.berkeley.edu/blog/feed.xml` | Academic |
| Karpathy | `karpathy.bearblog.dev/feed/` | Researcher |
| Lilian Weng | `lilianweng.github.io/index.xml` | Researcher |
| Chris Olah | `colah.github.io/rss.xml` | Researcher |
| Distill | `distill.pub/rss.xml` | Community |

### Customize Research Interests

Edit `config.yaml`:

```yaml
research_interests: |
  You are a Senior Principal Researcher at a top-tier AI lab.
  
  ## What You're Hunting For
  1. Paradigm Shifts: Papers that challenge existing dogmas
  2. First-Principles Elegance: Strong mathematical foundations
  3. Scaling Insights: What actually works at scale
  
  ## Specific Technical Interests
  - Generative Models: Diffusion, Flow Matching, Autoregressive
  - Reasoning & System 2: CoT, Latent Reasoning, Test-time Compute
  - Representation Learning: JEPA, Contrastive Learning
  - AI Safety & Alignment: Interpretability, Scalable Oversight
  
  ## What You DESPISE
  - Incremental SOTA chasing
  - Prompt engineering as research
  - Pure benchmarks without insights
```

### Configure Keywords

```yaml
keywords:
  # Tier 1: Precision strikes
  - diffusion language model
  - test-time compute
  - mechanistic interpretability
  
  # Tier 2: Wide net (pair with exclude_keywords)
  - LLM
  - scaling law
  - foundation model

exclude_keywords:
  - medical
  - biomedical
  - 3D
  - video generation
```

### Use Different LLMs

```bash
# OpenAI
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_MODEL=gpt-4o

# Claude (via Anthropic API)
export LLM_BASE_URL=https://api.anthropic.com/v1
export LLM_MODEL=claude-sonnet-4-20250514

# DeepSeek
export LLM_BASE_URL=https://api.deepseek.com/v1
export LLM_MODEL=deepseek-chat

# Gemini (via OpenAI-compatible endpoint)
export LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
export LLM_MODEL=gemini-2.0-flash-exp

# Local (Ollama)
export LLM_BASE_URL=http://localhost:11434/v1
export LLM_MODEL=llama3
```

### Cost Optimization

Use a **cheaper model for filtering**, stronger model for summarization:

```bash
# Filtering (called 2x per paper) - use cheap model
export LLM_FILTER_MODEL=gpt-4o-mini
export LLM_FILTER_BASE_URL=https://api.openai.com/v1

# Summarization (called once) - use better model
export LLM_MODEL=gpt-4o
export LLM_BASE_URL=https://api.openai.com/v1
```

---

## 🎨 Report Example

### 📢 Blog Highlights

> **2025 LLM Year in Review — Andrej Karpathy**
> 
> 📍 Andrej Karpathy's Blog
>
> **🎯 Why This Matters**: Karpathy 是少数既懂 engineering 又懂 research 的人，他的年度总结是理解 field direction 的最佳 single source。
>
> **📌 Key Insights**:
> - **Reasoning models 崛起**: o1-style models 成为主流，test-time compute scaling 是关键
> - **Tokenization 仍是瓶颈**: 他认为 continuous tokenization 可能是下一个突破点
> - **Multimodal 进展**: Vision-language models 从 novelty 变成 commodity
>
> **🔗 Action Items**: 去读他提到的 "Scaling Test-Time Compute" 论文，关注 tokenization 研究方向

---

### 🏆 Editor's Choice

> **Diffusion Language Models Learn Latent Reasoning**
> 
> **Verdict**: 这是我今天看到的唯一有"aha moment"的工作。将discrete diffusion用于推理任务，而不是generation，视角新颖。GitHub已获800+ stars，Reddit上关于"reasoning in latent space"的讨论非常热烈。
> 
> **Signal**: GitHub repo with 823 stars. Active Reddit discussion on implications for o1-style reasoning. HuggingFace community highly engaged.

### 🔬 Deep Dive

**👥 Authors**: Zhang et al. | Stanford, OpenAI

**🎯 The "Aha" Moment**: 传统diffusion models用于生成，这篇将其用于推理。Core idea: reasoning是一个在latent space中的iterative refinement过程，而不是token-by-token的autoregressive生成。社区反响热烈，认为这可能是post-CoT时代的新范式。

**🔧 Methodology**: 使用continuous diffusion在embedding space操作，训练时引入"reasoning checkpoints"强制模型学会分步推理。关键trick是引入了specialized noise schedule for logical consistency。

**📊 Reality Check**: GSM8K上达到89.2%（vs GPT-4的 92%），但在multi-hop推理上超越了CoT baseline 12个点。社区指出代码复现较容易，已有3个独立复现。

**💡 My Take**: 值得跟进。如果scaling law成立，这可能是reasoning的新方向。已加入复现队列。

### 🌀 Signals & Noise

**📖 Worth Skimming**
- Google's Year in Review — 快速扫一眼 8 个 breakthrough areas

**🚫 Pass**
- Chemical Hygiene (Karpathy) — 与 AI 无关的个人博客
- One in a Million (OpenAI) — 纯 marketing/PR 内容
- 40 AI Tips (Google) — 面向普通用户，对 researcher 无价值

---

## 🛠️ Advanced Features

### PDF Multimodal Input

For Claude and Gemini, full PDF is sent directly to the model:

```yaml
extract_fulltext: true
pdf_max_pages: 15  # Limit pages to save tokens
```

### Manual Paper Additions

Create `manual_papers.json`:

```json
{
  "papers": [
    {
      "title": "My Favorite Paper",
      "abstract": "...",
      "url": "https://arxiv.org/abs/2401.xxxxx",
      "notes": "Recommended by colleague"
    }
  ]
}
```

Or just add URLs (metadata auto-fetched):

```json
{
  "papers": [
    "https://arxiv.org/abs/2401.xxxxx",
    "https://arxiv.org/abs/2402.xxxxx"
  ]
}
```

### Operational Notes (Dedup + Memory + Daily Ops)

#### Dedup behavior (important)

- Paper fetch dedup key is `arxiv_id` first, else `url` (cross-source paper dedup at fetch stage).
- Paper dedup is **not** title-based by default.
- Blog dedup before report is by exact `url`.
- Report sections are generated by LLM. If the model repeats one paper in multiple sections (for example Editor's Choice and Deep Dive), this is currently allowed unless post-processing is added.

#### Semantic memory behavior

- Memory file: `semantic_scholar_memory.json`.
- Memory uses unified cross-source keys:
  - `arxiv:<id>` (canonical when available)
  - `semantic:<id>` plus legacy raw semantic id (migration compatibility)
  - `hf:<normalized-url>` fallback when no arXiv id exists
- Suppression applies across Semantic Scholar, arXiv, and HuggingFace.
- Only final papers that are actually present as links in rendered report HTML are marked as `seen`.
- Seen suppression window is controlled by `semantic_seen_ttl_days`.
- Memory size is capped by `semantic_memory_max_ids` (oldest entries are pruned).

#### GitHub Actions memory persistence model

- Workflow loads memory from `memory-state` branch before running pipeline.
- Workflow writes updated memory back to `memory-state` branch after run.
- Main code branch remains focused on code/config changes; memory churn is isolated.

#### Local + remote workflow tips

- Local dry-run will update local `semantic_scholar_memory.json`.
- Committing local memory is acceptable in this project (state file), but rebase/pull before push is still recommended if Actions updated remote state recently.
- `openspec/` artifacts are local workflow files (gitignored in this repo by default), so planning/spec drafts do not pollute normal code history unless you intentionally track them.
- Safe order for day-to-day changes:
  1. code change
  2. `git add` + `git commit`
  3. `git pull --rebase origin main`
  4. resolve conflicts if any
  5. `git push`

#### Manual action inputs (`days_back`)

- In GitHub Actions, open `Daily Paper Digest` -> `Run workflow`.
- `days_back` controls how many days of papers are fetched (`--days` in CLI).
- `dry_run=true` generates preview artifact (`paper-report`) without sending email.
- Feedback files are uploaded as `feedback-artifacts-<run_id>.zip` for each run.

#### Troubleshooting

- `LLM filter: Could not parse response (batch offset X)`:
  - Cause: model returned non-JSON/empty/invalid batch output.
  - Debug artifacts are saved in `llm_filter_debug/` with prompt + raw response.
  - Try a more stable filter model/base URL, then rerun.
- "Total papers" in report can look larger than unique visible picks:
  - Count may refer to upstream candidate pool while rendered sections show only selected subsets.
- Repeated paper/blog in multiple report sections:
  - Usually caused by LLM output structure, not source fetch dedup.
  - Add post-generation section-level dedup if strict uniqueness is required.

### Disable Features

```bash
# Disable blog fetching
python main.py --no-blogs

# Disable community research (if no Tavily API key)
unset TAVILY_API_KEY
python main.py --dry-run
```

---

## 🤝 Contributing

Contributions welcome! Areas for improvement:

- [x] ~~Blog source integration~~ ✅ Done!
- [x] Additional paper sources (Semantic Scholar) ✅ Done
- [ ] Additional paper sources (OpenReview)
- [ ] More research enrichment signals (citation counts, author h-index)
- [ ] Multi-language support
- [ ] Web UI / Chatbot integration
- [ ] Vector database for historical papers

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- Inspired by [Karpathy's blog](https://karpathy.github.io/) and the "senior researcher" mindset
- Built on top of [arXiv API](https://arxiv.org/help/api), [HuggingFace](https://huggingface.co/), and [Tavily](https://tavily.com/)
- Blog feeds from OpenAI, Anthropic, DeepMind, Google AI, Meta AI, BAIR, and individual researchers
- Community feedback from AI research communities on Reddit and Twitter

---

## 📞 Contact

- GitHub: [@gaoxin492](https://github.com/gaoxin492)
- Issues: [GitHub Issues](https://github.com/gaoxin492/PaperFeeder/issues)

---

**⚡ Pro Tip**: Start with `--dry-run` to preview reports locally, then follow [DEPLOY.md](DEPLOY.md) to set up **free automated daily delivery** via GitHub Actions!

**🎯 Deployment**: For daily automated paper digests, see [DEPLOY.md](DEPLOY.md) for:
- 🆓 **GitHub Actions** setup (recommended, no server needed)
- 🖥️ Server deployment with cron jobs
- 🐳 Docker containerization

**Total setup time: ~5 minutes** ⏱️

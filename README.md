# 📚 PaperFeeder

> **AI Agent for Daily Paper Digest**  
> Hunt for "The Next Big Thing", despise incremental work.

An intelligent paper recommendation system that automatically fetches, filters, researches, and summarizes academic papers from arXiv and HuggingFace. Powered by LLM agents and community signal enrichment.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ Key Features

### 🤖 **AI Agent Workflow**
Six-stage intelligent pipeline that mimics how a senior researcher screens papers:

```
Fetch → Keyword Filter → LLM Coarse Filter → Research & Enrichment → LLM Fine Filter → Synthesis
 (Recall)    (Cast Wide Net)    (Quick Score)      (Community Signals)       (Deep Ranking)     (Report)
```

### 🔍 **Community Signal Enrichment**
- Uses **Tavily API** to search GitHub, Reddit, Twitter, HuggingFace
- Extracts: GitHub stars, community discussions, reproducibility issues
- Integrates external validation into paper evaluation

### 🎯 **Two-Stage LLM Filtering**
- **Stage 1 (Coarse)**: Fast screening based on title + abstract → Top 20
- **Stage 2 (Fine)**: Deep ranking with community signals → Top 3-5

### 📰 **"Editor's Choice" Style Reports**
- Senior Principal Researcher persona (OpenAI/DeepMind/Anthropic caliber)
- 犀利点评，中英文夹杂 (Sharp commentary, bilingual)
- Sections: 🏆 Editor's Choice, 🔬 Deep Dive, 🌀 Signals & Noise

### 🔧 **Flexible & Extensible**
- Supports any OpenAI-compatible LLM (OpenAI, Claude, Gemini, DeepSeek, Qwen, local models)
- PDF multimodal input for deep analysis (Claude, Gemini)
- Customizable research interests and filtering criteria

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

# Fetch last 3 days
python main.py --days 3
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

## 🏗️ Architecture

### AI Agent Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: FETCH (Recall)                                      │
│ • arXiv (cs.LG, cs.CL, cs.CV, etc.)                         │
│ • HuggingFace Daily Papers                                   │
│ • Manual additions                                           │
└────────────────────┬────────────────────────────────────────┘
                     │ ~50-100 papers
┌────────────────────▼────────────────────────────────────────┐
│ Stage 2: KEYWORD FILTER (Cast Wide Net)                     │
│ • Match keywords in title + abstract                        │
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
                     │ 3-5 papers
┌────────────────────▼────────────────────────────────────────┐
│ Stage 6: SYNTHESIS (Report Generation)                      │
│ • Senior Principal Researcher persona                       │
│ • PDF multimodal input (if supported)                       │
│ • Output: HTML report with MathJax support                  │
└─────────────────────────────────────────────────────────────┘
```

### Module Overview

```
PaperFeeder/
├── main.py              # AI Agent orchestration
├── sources.py           # Paper fetchers (arXiv, HuggingFace, Manual)
├── filters.py           # Two-stage LLM filtering
├── researcher.py        # Tavily-powered community research (NEW)
├── summarizer.py        # Report generation with community signals
├── llm_client.py        # Universal LLM client (OpenAI-compatible)
├── emailer.py           # Email delivery (Resend, SendGrid, File)
├── models.py            # Data models (Paper, Author, etc.)
├── config.py            # Configuration management
└── config.yaml          # User configuration
```

---

## 📖 Usage Guide

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

### Disable Community Research

If you don't have Tavily API key:

```bash
# System will auto-detect and use mock researcher
unset TAVILY_API_KEY
python main.py --dry-run
```

---

## 🤝 Contributing

Contributions welcome! Areas for improvement:

- [ ] Additional paper sources (Semantic Scholar, OpenReview)
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
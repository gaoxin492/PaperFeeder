"""
Paper summarization using any LLM.
Generates daily digest with summaries and insights.

Persona: Senior Principal Researcher at a Top-Tier AI Lab
Philosophy: Hunt for "The Next Big Thing", despise incremental work.

UPGRADED: 
- Now includes community signals (research_notes) in analysis.
- NEW: Supports blog posts from priority sources (OpenAI, Anthropic, etc.)
- IMPROVED: Blog posts are selectively filtered (1-3 picks) with highlights and deep dive
"""

from __future__ import annotations

import asyncio
import base64
import aiohttp
from datetime import datetime
from typing import Optional, List

from models import Paper
from llm_client import LLMClient


class PaperSummarizer:
    """Generate paper summaries and insights using any LLM."""
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        research_interests: str = "",
        debug_save_pdfs: bool = False,
        debug_pdf_dir: str = "debug_pdfs",
        pdf_max_pages: int = 10,
    ):
        self.client = LLMClient(
            api_key=api_key, 
            base_url=base_url, 
            model=model,
            debug_save_pdfs=debug_save_pdfs,
            debug_pdf_dir=debug_pdf_dir,
            pdf_max_pages=pdf_max_pages
        )
        self.research_interests = research_interests
    
    def _build_prompt(
        self, 
        papers: list[Paper], 
        papers_with_pdf: list[Paper] = None, 
        failed_pdf_papers: list[Paper] = None,
        blog_posts: list[Paper] = None,
    ) -> str:
        """
        构建 Senior Principal Researcher 视角的 prompt。
        
        核心理念:
        - 不是"相关性"筛选，而是"惊奇度"和"范式转移"筛选
        - 犀利点评，拒绝废话
        - 中英文夹杂（专有名词英文）
        
        UPGRADED:
        - 现在包含 research_notes (社区信号)
        - NEW: 支持博客帖子（来自 priority 源）
        - IMPROVED: 博客筛选独立于论文，只在 Blog Highlights 和 Deep Dive 中出现
        """
        
        failed_pdf_set = set(failed_pdf_papers) if failed_pdf_papers else set()
        blog_posts = blog_posts or []
        
        # 构建论文列表，包含 research_notes（社区信号）
        papers_info = []
        for i, paper in enumerate(papers, 1):
            authors_str = ", ".join([a.name for a in paper.authors[:5]])
            if len(paper.authors) > 5:
                authors_str += " et al."
            
            has_pdf = papers_with_pdf and paper in papers_with_pdf
            is_failed = paper in failed_pdf_set
            
            if is_failed:
                pdf_note = " [⚠️ PDF失败]"
            elif has_pdf:
                pdf_note = " [📄 PDF]"
            else:
                pdf_note = ""
            
            # 检查是否有 research_notes（联网调研笔记）
            community_signal = ""
            if hasattr(paper, 'research_notes') and paper.research_notes:
                community_signal = f"\n   🔍 Community Signals: {paper.research_notes}"
            
            papers_info.append(
                f"{i}. {paper.title}{pdf_note}\n"
                f"   Authors: {authors_str}\n"
                f"   URL: {paper.url}"
                f"{community_signal}"
            )
        
        # 构建博客帖子列表
        blog_info = []
        if blog_posts:
            for i, post in enumerate(blog_posts, 1):
                source = getattr(post, 'blog_source', 'Unknown')
                # 去掉标题中的 [Blog] 前缀（如果有）
                title = post.title
                if title.startswith("[Blog] "):
                    title = title[7:]
                
                # 提供更多内容供 LLM 判断
                content_preview = post.abstract[:500] if post.abstract else "No content preview"
                
                blog_info.append(
                    f"{i}. {title}\n"
                    f"   Source: {source}\n"
                    f"   URL: {post.url}\n"
                    f"   Content: {content_preview}..."
                )
        
        pdf_context = ""
        if papers_with_pdf:
            successful_count = len(papers_with_pdf) - len(failed_pdf_set)
            pdf_context = f"\n\n📄 {successful_count} PDFs provided for deep analysis."
            if failed_pdf_set:
                pdf_context += f" ({len(failed_pdf_set)} failed, using abstract only)"
        
        # === SYSTEM PROMPT: Senior Principal Researcher Persona ===
        system_prompt = """You are a Senior Principal Researcher at a top-tier AI lab (OpenAI/DeepMind/Anthropic caliber), screening papers AND blog posts for your research team.

## Your Philosophy
- You DESPISE incremental work. "Beat SOTA by 0.2%" makes you yawn.
- You hunt for **Paradigm Shifts**, **Counter-intuitive Findings**, and **Mathematical Elegance**.
- You value **First Principles Thinking** over empirical bag-of-tricks.
- You care about **what scales** and **what actually matters**.

## Your Evaluation Lens
For each paper AND blog post, you instinctively assess:
- **Surprise (惊奇度)**: Does it challenge my priors? Is there an "aha" moment?
- **Rigor (严谨度)**: Is the content substantive, or is it just marketing fluff?
- **Impact (潜在影响)**: Could this change how we build systems? Or is it a footnote?
- **Relevance (相关性)**: Is it actually about AI/ML research, or off-topic (health, product announcements, etc.)?

## Your Communication Style
- 犀利、专业、不废话
- 中英文夹杂（专有名词保留英文，如 "diffusion"、"scaling law"、"test-time compute"）
- 你可以毒舌，但要有建设性
- 直接给判断，不要 "on the other hand..." 这种模棱两可

## CRITICAL: Blog Post Filtering
- NOT all blog posts are worth reading!
- Filter OUT: marketing content, product announcements, off-topic posts (health, chemical hygiene, etc.)
- Keep ONLY: technical deep dives, year-in-review posts, research insights, methodology discussions
- A blog post from a famous source can still be SKIP-worthy if it's not about AI research"""

        # === USER PROMPT ===
        # Build the content sections
        papers_section = ""
        if papers:
            papers_section = f"""
## Today's Paper Pool ({len(papers)} papers)
{chr(10).join(papers_info)}{pdf_context}
"""
        
        blogs_section = ""
        if blog_posts:
            blogs_section = f"""
## 📝 Blog Posts from Priority Sources ({len(blog_posts)} posts)
**NOTE: These need filtering too! Not all are worth reading.**

{chr(10).join(blog_info)}
"""

        user_prompt = f"""## My Research Interests
{self.research_interests}
{blogs_section}{papers_section}
---

## Your Task

请以 Senior Principal Researcher 的视角审阅这批内容，输出 **clean HTML**（不要 html/head/body 标签）。

**CRITICAL INSTRUCTIONS**:
1. 博客也需要筛选！不是所有博客都值得读。过滤掉：marketing content、product announcements、与 AI 研究无关的内容。
2. 只选出 **Top 1-3 篇最值得深读的博客**，并进行详细分析。
3. 如果某天的博客都是 marketing fluff 或 off-topic，可以不选任何博客。

---

## Output Structure
"""

        # Blog section prompt (only if blogs exist)
        if blog_posts:
            user_prompt += """
### Section 0: 📢 Blog Highlights (1-3 Picks)

从所有博客中筛选出 **1-3 篇最值得关注的**（不要硬凑数，不足3篇也没问题）。筛选标准：
- ✅ 技术深度文章（如 Karpathy 的年度总结、技术 deep dive）
- ✅ 研究方向洞察（如实验室的 research roadmap）
- ✅ 方法论讨论（如 prompt injection 防御策略）
- ❌ 纯 marketing/PR 内容（如 "Celebrating X customers"）
- ❌ Product announcements（如 "60 AI announcements"）
- ❌ 与 AI 研究无关的内容（如健康、化学品等）

**如果没有值得关注的博客，这个 section 可以完全跳过，不要显示任何内容。**

每篇入选博客只需 **1-2 句话简短总结**：
- **Blog Title** (链接)
- **Source**: 来源
- **Summary**: 1-2句话说明这篇博客的核心内容和价值

HTML 格式：
```html
<div class="blog-highlights">
<h2>📢 Blog Highlights</h2>
<p class="section-desc">Top picks from industry blogs — filtered for research value</p>

<div class="blog-summary">
<h3><a href="URL">Blog Title</a></h3>
<p class="source">📍 Source Name</p>
<p class="summary">1-2句话简短总结这篇博客的核心内容和价值...</p>
</div>

</div>
```

如果没有值得关注的博客：
```html
<div class="blog-highlights">
<h2>📢 Blog Highlights</h2>
<p class="no-highlights">今天的博客主要是 product announcements 和 marketing content，没有值得关注的技术内容。</p>
</div>
```

---
"""

        # Papers section prompt
        user_prompt += """
### Section 1: 🏆 Editor's Choice (Top 1-5 Papers)

只选**真正值得读的论文**（不包含博客，1-5篇）。没有就留空，不要凑数。

每篇包含：
- **Paper Title** (链接)
- **Verdict**: 一句话犀利点评，说明为什么入选
- **Signal**: 如果有社区热度/讨论，简要提及；没有就写 "N/A"

HTML 格式：
```html
<div class="editors-choice">
<h2>🏆 Editor's Choice</h2>
<div class="choice-item">
<h3><a href="URL">Paper Title</a></h3>
<p class="verdict"><b>Verdict:</b> 一句话点评...</p>
<p class="signal"><b>Signal:</b> 社区热度/讨论...</p>
</div>
</div>
```

如果没有值得入选的论文：
```html
<div class="editors-choice">
<h2>🏆 Editor's Choice</h2>
<p class="no-choice">今天没有让我眼前一亮的论文。</p>
</div>
```

---

### Section 2: 🔬 Deep Dive

对 Editor's Choice 入选的**论文**和 Section 0 入选的**博客**进行深度分析。

**论文分析**：
每篇包含：
- **👥 Authors**: 作者 + 单位（1行）
- **🎯 The "Aha" Moment**: 这篇论文最反直觉/最有趣的点是什么？（2-3句）
- **🔧 Methodology**: 具体怎么做的？技术核心是什么？（3-4句，要有细节）
- **📊 Reality Check**: 实验结果可信吗？有哪些 caveats？（2-3句，带数字）
- **💡 My Take**: 作为 researcher，你会怎么行动？复现/引用/跟进/忽略？（1-2句）

**博客分析**：
每篇包含：
- **🎯 Why This Matters**: 为什么这篇博客值得深读（具体说明技术价值）
- **📌 Key Insights**: 3-5 个核心观点/takeaways，要有具体内容
- **🔗 Action Items**: 读完后你会做什么（关注方向、读相关论文等）

HTML 格式：
```html
<div class="deep-dive">
<h2>🔬 Deep Dive</h2>

<!-- 论文 Deep Dive -->
<div class="paper">
<h3 class="paper-title"><span class="badge high">🔥</span><a href="URL">Paper Title</a></h3>
<div class="paper-body">
<p class="authors">👥 Author1, Author2, ... | Institution1, Institution2</p>
<p><b>🎯 The "Aha" Moment:</b> ...</p>
<p><b>🔧 Methodology:</b> ...</p>
<p><b>📊 Reality Check:</b> ...</p>
<p><b>💡 My Take:</b> ...</p>
</div>
</div>

<!-- 博客 Deep Dive -->
<div class="blog">
<h3 class="blog-title"><span class="badge blog">📝</span><a href="URL">Blog Title</a></h3>
<div class="blog-body">
<p><b>🎯 Why This Matters:</b> 具体说明为什么值得深读...</p>
<div class="insights">
<p><b>📌 Key Insights:</b></p>
<ul>
<li><b>Insight 1:</b> 具体内容...</li>
<li><b>Insight 2:</b> 具体内容...</li>
<li><b>Insight 3:</b> 具体内容...</li>
</ul>
</div>
<p><b>🔗 Action Items:</b> 读完后的行动...</p>
</div>
</div>

</div>
```

Badge 规则: `high` (🔥 paradigm-shifting), `medium` (⭐ solid contribution), `low` (📄 incremental), `blog` (📝 blog deep dive)

---

### Section 3: 🌀 Signals & Noise

对**剩余论文**中**有价值但不够突出**的进行快速标注。

只列出 **[Worth Skimming]** 的论文：
- 有一些价值或有趣的点，可以快速翻翻
- 每篇只需 1 句话说明为什么值得一看

**完全不提 Pass 的论文**（节省 token，不值得浪费注意力）。

HTML 格式：
```html
<div class="signals-noise">
<h2>🌀 Signals & Noise</h2>

<div class="skim-list">
<h4>📖 Worth Skimming</h4>
<ul>
<li><a href="URL">Paper Title</a> — 一句话理由</li>
</ul>
</div>

</div>
```

---

## Critical Requirements

1. **博客也要筛选**: 不是所有博客都值得读！过滤掉 marketing、product announcements、off-topic 内容。
2. **Be Ruthless**: 宁缺毋滥。如果今天没有好内容，各 section 可以是空的。
3. **Be Specific**: 不要说 "interesting"，要说具体 interesting 在哪里。
4. **深度分析要有干货**: Key Insights 要有具体内容，不要泛泛而谈。
5. **中英文夹杂**: 专有名词（如 diffusion, CoT, RLHF, scaling law）保留英文。
6. **Action-oriented**: 每篇深度分析都要给出"读完后该做什么"的建议。"""

        return {"system": system_prompt, "user": user_prompt}
    
    async def generate_report(
        self, 
        papers: list[Paper], 
        use_pdf_multimodal: bool = True,
        blog_posts: list[Paper] = None,
    ) -> str:
        """
        Generate the daily paper digest report.
        
        Args:
            papers: List of filtered papers to analyze
            use_pdf_multimodal: Whether to use PDF multimodal input
            blog_posts: List of priority blog posts (will be filtered by LLM)
        
        Returns:
            HTML report string
        """
        if not papers and not blog_posts:
            return self._wrap_html("<p>No papers or blog posts to review today.</p>", [], blog_posts)
        
        # Separate blog posts from papers if they're mixed together
        actual_papers = []
        actual_blogs = list(blog_posts) if blog_posts else []
        
        for paper in papers:
            if getattr(paper, 'is_blog', False):
                actual_blogs.append(paper)
            else:
                actual_papers.append(paper)
        
        # Remove duplicates from blogs
        seen_urls = set()
        unique_blogs = []
        for blog in actual_blogs:
            if blog.url not in seen_urls:
                seen_urls.add(blog.url)
                unique_blogs.append(blog)
        actual_blogs = unique_blogs
        
        papers_with_pdf = []
        failed_pdf_papers = []
        
        # Process PDFs for papers only (not blogs)
        if use_pdf_multimodal and actual_papers:
            print(f"   📄 Processing {len(actual_papers)} PDFs individually...")
            
            for i, paper in enumerate(actual_papers, 1):
                print(f"      [{i}/{len(actual_papers)}] {paper.title[:40]}...")
                if not getattr(paper, "pdf_url", None):
                    failed_pdf_papers.append(paper)
                    paper._pdf_base64 = None
                    print("      ⚠️ No pdf_url, fallback to abstract-only")
                    continue
                pdf_content = await self.client._url_to_base64_async(
                    paper.pdf_url,
                    save_debug=getattr(self.client, 'debug_save_pdfs', False),
                    debug_dir=getattr(self.client, 'debug_pdf_dir', 'debug_pdfs'),
                    max_pages=getattr(self.client, 'pdf_max_pages', 10)
                )
                if pdf_content:
                    paper._pdf_base64 = pdf_content
                    papers_with_pdf.append(paper)
                else:
                    failed_pdf_papers.append(paper)
                    paper._pdf_base64 = None
        
        # Build prompt
        prompts = self._build_prompt(
            actual_papers, 
            papers_with_pdf, 
            failed_pdf_papers,
            blog_posts=actual_blogs
        )
        
        # Prepare messages for LLM
        messages = [
            {"role": "system", "content": prompts["system"]},
        ]
        
        # Build user content with PDFs
        user_content = []
        
        # Add PDFs first (for papers with PDF)
        for paper in papers_with_pdf:
            if paper not in failed_pdf_papers and hasattr(paper, '_pdf_base64') and paper._pdf_base64:
                user_content.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": paper._pdf_base64
                    },
                    "cache_control": {"type": "ephemeral"}
                })
        
        # Add text prompt
        user_content.append({
            "type": "text",
            "text": prompts["user"]
        })
        
        messages.append({"role": "user", "content": user_content})
        
        # Generate report
        try:
            content = await self.client.achat(messages, max_tokens=8000)
            
            # Combine papers and blogs for the wrap
            all_items = actual_papers + actual_blogs
            return self._wrap_html(content, all_items, actual_blogs)
            
        except Exception as e:
            error_msg = f"<p class='error'>Error generating report: {str(e)}</p>"
            return self._wrap_html(error_msg, actual_papers, actual_blogs)
    
    def _wrap_html(self, content: str, papers: list[Paper], blog_posts: list[Paper] = None) -> str:
        """Wrap content in HTML template with styling."""
        today = datetime.now()
        today_cn = today.strftime("%Y年%m月%d日")
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekdays[today.weekday()]
        
        # Count items
        paper_count = len([p for p in papers if not getattr(p, 'is_blog', False)])
        blog_count = len(blog_posts) if blog_posts else 0
        
        # Build meta string
        if blog_count > 0 and paper_count > 0:
            meta_str = f"{paper_count} papers + {blog_count} blogs reviewed"
        elif blog_count > 0:
            meta_str = f"{blog_count} blogs reviewed"
        else:
            meta_str = f"{paper_count} papers reviewed"
        
        return f"""<!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Paper Digest - {today.strftime("%Y-%m-%d")}</title>
        <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                background: #f0f2f5;
                padding: 10px;
                font-size: 15px;
            }}
            
            .container {{
                max-width: 920px;
                margin: 0 auto;
                background: #fff;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }}
            
            .header {{
                background-color: #1a1a2e;
                background: linear-gradient(135deg, #1a1a2e, #16213e);
                color: #fff;
                padding: 20px 24px;
                text-align: center;
                border-radius: 10px 10px 0 0;
            }}
            
            .header h1 {{ 
                font-size: 1.4em; 
                font-weight: 700; 
                letter-spacing: -0.5px;
            }}
            .header .meta {{ 
                opacity: 0.85; 
                font-size: 0.9em; 
                margin-top: 4px; 
            }}
            .header .persona {{
                font-size: 0.75em;
                opacity: 0.6;
                margin-top: 8px;
                font-style: italic;
            }}
            
            .content {{ padding: 20px 24px; }}
            
            h2 {{
                font-size: 1.1em;
                font-weight: 700;
                color: #1a1a2e;
                margin: 24px 0 12px 0;
                padding-bottom: 8px;
                border-bottom: 2px solid #eee;
            }}
            
            h3 {{ font-size: 1em; color: #1a1a1a; font-weight: 600; }}
            h4 {{ font-size: 0.95em; color: #444; font-weight: 600; margin: 12px 0 8px 0; }}
            
            /* Bold text styling */
            b, strong {{ font-weight: 600; color: #1a1a2e; }}
            
            /* Code styling */
            code {{
                background: #f5f5f5;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 0.9em;
                color: #d73a49;
            }}
            
            /* Math styling */
            .MathJax {{ font-size: 1.1em !important; }}
            
            /* Blog Highlights Section (NEW - Deep Dive style) */
            .blog-highlights {{
                background: linear-gradient(135deg, #e8f4fd, #d6eaf8);
                border: 1px solid #85c1e9;
                border-radius: 8px;
                padding: 16px 20px;
                margin-bottom: 20px;
            }}
            
            .blog-highlights h2 {{
                color: #2874a6;
                margin: 0 0 8px 0;
                padding: 0;
                border: none;
            }}
            
            .blog-highlights .section-desc {{
                font-size: 0.85em;
                color: #5d6d7e;
                margin-bottom: 14px;
                font-style: italic;
            }}
            
            .blog-highlights .no-highlights {{
                font-size: 0.9em;
                color: #7f8c8d;
                font-style: italic;
            }}

            .blog-summary {{
                background: #fff;
                border-radius: 6px;
                padding: 12px 16px;
                margin-bottom: 10px;
                border-left: 3px solid #3498db;
            }}

            .blog-summary:last-child {{ margin-bottom: 0; }}

            .blog-summary h3 {{
                font-size: 0.95em;
                font-weight: 600;
                margin-bottom: 6px;
            }}

            .blog-summary h3 a {{
                color: #1a1a1a;
                text-decoration: none;
            }}
            .blog-summary h3 a:hover {{ color: #2874a6; }}

            .blog-summary .source {{
                font-size: 0.8em;
                color: #7f8c8d;
                margin-bottom: 8px;
            }}

            .blog-summary .summary {{
                font-size: 0.9em;
                color: #444;
                line-height: 1.4;
            }}
            
            /* Editor's Choice Section */
            .editors-choice {{
                background: linear-gradient(135deg, #fff9e6, #fff5d6);
                border: 1px solid #f0d060;
                border-radius: 8px;
                padding: 16px 20px;
                margin-bottom: 20px;
            }}
            
            .editors-choice h2 {{
                color: #b8860b;
                margin: 0 0 12px 0;
                padding: 0;
                border: none;
            }}
            
            .choice-item {{
                background: #fff;
                border-radius: 6px;
                padding: 12px 16px;
                margin-bottom: 12px;
                border-left: 4px solid #daa520;
            }}
            
            .choice-item:last-child {{ margin-bottom: 0; }}
            
            .choice-item h3 {{
                font-size: 0.95em;
                margin-bottom: 8px;
            }}
            
            .choice-item h3 a {{ 
                color: #1a1a1a; 
                text-decoration: none; 
            }}
            .choice-item h3 a:hover {{ color: #b8860b; }}
            
            .verdict {{ font-size: 0.9em; color: #333; margin-bottom: 4px; }}
            .signal {{ font-size: 0.85em; color: #666; }}
            .no-choice {{ font-size: 0.9em; color: #888; font-style: italic; }}
            
            /* Deep Dive Section */
            .deep-dive {{
                margin-bottom: 20px;
            }}
            
            .paper {{
                padding: 16px 18px;
                margin-bottom: 14px;
                background: #fafafa;
                border-radius: 8px;
                border-left: 4px solid #1a1a2e;
            }}
            
            .paper-title {{
                font-size: 1em;
                font-weight: 600;
                margin-bottom: 12px;
                line-height: 1.4;
            }}
            
            .paper-title a {{ color: #1a1a1a; text-decoration: none; }}
            .paper-title a:hover {{ color: #4a4a8a; }}
            
            .badge {{
                display: inline-block;
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 0.7em;
                margin-right: 8px;
                vertical-align: middle;
                font-weight: 500;
            }}
            
            .badge.high {{ background: #ffe0e0; color: #c0392b; }}
            .badge.medium {{ background: #fff3cd; color: #b7791f; }}
            .badge.low {{ background: #e8e8e8; color: #666; }}
            .badge.blog {{ background: #e8f4fd; color: #2874a6; }}
            
            .paper-body {{ font-size: 0.9em; color: #444; }}
            .paper-body p {{ margin-bottom: 10px; }}
            .paper-body b {{ color: #1a1a2e; }}
            .paper-body .authors {{
                color: #666;
                font-size: 0.85em;
                margin-bottom: 12px;
                padding-bottom: 10px;
                border-bottom: 1px dashed #ddd;
            }}

            /* Blog Deep Dive in Deep Dive section */
            .blog {{
                padding: 16px 18px;
                margin-bottom: 14px;
                background: #f0f8ff;
                border-radius: 8px;
                border-left: 4px solid #3498db;
            }}

            .blog-title {{
                font-size: 1em;
                font-weight: 600;
                margin-bottom: 12px;
                line-height: 1.4;
            }}

            .blog-title a {{ color: #1a1a1a; text-decoration: none; }}
            .blog-title a:hover {{ color: #2874a6; }}

            .blog-body {{ font-size: 0.9em; color: #444; }}
            .blog-body p {{ margin-bottom: 10px; }}
            .blog-body b {{ color: #2874a6; }}
            .blog-body .insights ul {{
                margin: 8px 0 12px 20px;
                padding: 0;
            }}
            .blog-body .insights li {{
                margin-bottom: 6px;
                color: #444;
            }}
            
            /* Signals & Noise Section */
            .signals-noise {{
                background: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 8px;
                padding: 16px 20px;
                margin-top: 20px;
            }}
            
            .signals-noise h2 {{
                color: #495057;
                margin: 0 0 12px 0;
                padding: 0;
                border: none;
            }}
            
            .skim-list {{
                margin-bottom: 12px;
            }}

            .skim-list h4 {{ color: #28a745; }}

            .skim-list ul {{
                padding-left: 20px;
                margin: 0;
            }}

            .skim-list li {{
                font-size: 0.88em;
                color: #555;
                padding: 3px 0;
            }}

            .skim-list a {{ color: #28a745; }}
            
            /* Warning */
            .warning {{
                background: #fff3cd;
                border: 1px solid #ffc107;
                border-radius: 6px;
                padding: 10px 14px;
                margin-bottom: 14px;
                font-size: 0.85em;
                color: #856404;
            }}
            
            .warning a {{ color: #856404; }}
            
            /* Error */
            .error {{
                background: #f8d7da;
                border: 1px solid #f5c6cb;
                border-radius: 6px;
                padding: 10px 14px;
                margin-bottom: 14px;
                font-size: 0.85em;
                color: #721c24;
            }}
            
            .footer {{
                text-align: center;
                padding: 14px;
                font-size: 0.75em;
                color: #999;
                border-top: 1px solid #eee;
            }}
            
            a {{ color: #4a4a8a; }}
            
            @media (max-width: 600px) {{
                body {{ padding: 6px; font-size: 14px; }}
                .content {{ padding: 14px 16px; }}
                .header {{ padding: 14px 16px; }}
                .paper {{ padding: 12px 14px; }}
                .editors-choice, .signals-noise, .blog-highlights {{ padding: 12px 14px; }}
                .choice-item, .blog-summary {{ padding: 10px 12px; }}
            }}
        </style>
    </head>
        <body>
        <div class="container">
            <div class="header" style="background-color:#1a1a2e;background-image:linear-gradient(135deg,#1a1a2e,#16213e);color:#ffffff;">
                <h1 style="color:#ffffff;">📚 Paper Digest</h1>
                <div class="meta" style="color:#ffffff;">{today_cn} {weekday} · {meta_str}</div>
                <div class="persona" style="color:#d6d8e0;">Curated by PaperFeeder · No fluff, no hype</div>
            </div>
            
            <div class="content">
                {content}
            </div>
            
            <div class="footer">
                PaperFeeder · {self._get_unique_keywords(papers)}
            </div>
        </div>
    </body>
    </html>"""
    
    def _get_unique_keywords(self, papers: list[Paper]) -> str:
        """Get unique matched keywords."""
        keywords = set()
        for paper in papers:
            if hasattr(paper, 'matched_keywords'):
                keywords.update(paper.matched_keywords)
        return ", ".join(sorted(keywords)[:8]) if keywords else "AI Research"


# Backward compatibility
ClaudeSummarizer = PaperSummarizer

"""
Paper summarization using any LLM.
Generates daily digest with summaries and insights.

Persona: Senior Principal Researcher at a Top-Tier AI Lab
Philosophy: Hunt for "The Next Big Thing", despise incremental work.

UPGRADED: Now includes community signals (research_notes) in analysis.
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
    
    def _build_prompt(self, papers: list[Paper], papers_with_pdf: list[Paper] = None, failed_pdf_papers: list[Paper] = None) -> str:
        """
        构建 Senior Principal Researcher 视角的 prompt。
        
        核心理念:
        - 不是"相关性"筛选，而是"惊奇度"和"范式转移"筛选
        - 犀利点评，拒绝废话
        - 中英文夹杂（专有名词英文）
        
        UPGRADED: 现在包含 research_notes (社区信号)
        """
        
        failed_pdf_set = set(failed_pdf_papers) if failed_pdf_papers else set()
        
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
        
        pdf_context = ""
        if papers_with_pdf:
            successful_count = len(papers_with_pdf) - len(failed_pdf_set)
            pdf_context = f"\n\n📄 {successful_count} PDFs provided for deep analysis."
            if failed_pdf_set:
                pdf_context += f" ({len(failed_pdf_set)} failed, using abstract only)"
        
        # === SYSTEM PROMPT: Senior Principal Researcher Persona ===
        system_prompt = """You are a Senior Principal Researcher at a top-tier AI lab (OpenAI/DeepMind/Anthropic caliber), screening papers for your research team.

## Your Philosophy
- You DESPISE incremental work. "Beat SOTA by 0.2%" makes you yawn.
- You hunt for **Paradigm Shifts**, **Counter-intuitive Findings**, and **Mathematical Elegance**.
- You value **First Principles Thinking** over empirical bag-of-tricks.
- You care about **what scales** and **what actually matters**.

## Your Evaluation Lens
For each paper, you instinctively assess:
- **Surprise (惊奇度)**: Does it challenge my priors? Is there an "aha" moment?
- **Rigor (严谨度)**: Is the evaluation convincing, or is it cherry-picked toy experiments?
- **Impact (潜在影响)**: Could this change how we build systems? Or is it a footnote?
- **Community Signal (社区信号)**: What do external signals say? High GitHub stars? Hot discussions? Or overhyped?

## Your Communication Style
- 犀利、专业、不废话
- 中英文夹杂（专有名词保留英文，如 "diffusion"、"scaling law"、"test-time compute"）
- 你可以毒舌，但要有建设性
- 直接给判断，不要 "on the other hand..." 这种模棱两可
- **CRITICAL**: You MUST integrate community signals into your analysis when available"""

        # === USER PROMPT ===
        user_prompt = f"""## My Research Interests
{self.research_interests}

## Today's Paper Pool ({len(papers)} papers)
{chr(10).join(papers_info)}{pdf_context}

---

## Your Task

请以 Senior Principal Researcher 的视角审阅这批论文，输出 **clean HTML**（不要 html/head/body 标签）。

**IMPORTANT**: When papers have 🔍 Community Signals, you MUST incorporate them into your analysis. Examples:
- "虽然方法简单，但GitHub已获1k stars，Reddit上引发关于Scaling Law的激烈讨论"
- "作者团队知名，但社区反馈指出reproducibility issues"
- "看似incremental，但HuggingFace社区高度关注，可能有实用价值"

---

## Output Structure

### Section 1: 🏆 Editor's Choice (Top 1-3)

只选**真正值得读**的论文。没有就留空，不要凑数。

每篇包含：
- **Paper Title** (链接)
- **Verdict**: 一句话犀利点评，说明为什么入选（或为什么差点没入选）
  - **必须结合community signals**（如果有的话）
- **Signal**: 如果有社区热度/讨论，简要提及；没有就写 "N/A"

HTML 格式：
```html
<div class="editors-choice">
<h2>🏆 Editor's Choice</h2>
<div class="choice-item">
<h3><a href="URL">Paper Title</a></h3>
<p class="verdict"><b>Verdict:</b> 一句话点评（必须提及community signal如果有）...</p>
<p class="signal"><b>Signal:</b> 社区热度/讨论...</p>
</div>
</div>
```

如果没有值得入选的论文：
```html
<div class="editors-choice">
<h2>🏆 Editor's Choice</h2>
<p class="no-choice">今天没有让我眼前一亮的论文。都是 incremental work。</p>
</div>
```

---

### Section 2: 🔬 Deep Dive

对 Editor's Choice 入选的论文进行深度分析。

每篇包含：
- **👥 Authors**: 作者 + 单位（1行）
- **🎯 The "Aha" Moment**: 这篇论文最反直觉/最有趣的点是什么？（2-3句）
  - **如果有community signals，说明社区如何响应这个idea**
- **🔧 Methodology**: 具体怎么做的？技术核心是什么？（3-4句，要有细节）
- **📊 Reality Check**: 实验结果可信吗？有哪些 caveats？（2-3句，带数字）
  - **如果community signals提到reproducibility，必须讨论**
- **💡 My Take**: 作为 researcher，你会怎么行动？复现/引用/跟进/忽略？（1-2句）
  - **结合community validation进行判断**

HTML 格式：
```html
<div class="deep-dive">
<h2>🔬 Deep Dive</h2>

<div class="paper">
<h3 class="paper-title"><span class="badge high">🔥</span><a href="URL">Paper Title</a></h3>
<div class="paper-body">
<p class="authors">👥 Author1, Author2, ... | Institution1, Institution2</p>
<p><b>🎯 The "Aha" Moment:</b> ... (integrate community response if available)</p>
<p><b>🔧 Methodology:</b> ...</p>
<p><b>📊 Reality Check:</b> ... (mention reproducibility if discussed in community)</p>
<p><b>💡 My Take:</b> ... (factor in community validation)</p>
</div>
</div>

</div>
```

Badge 规则: `high` (🔥 paradigm-shifting), `medium` (⭐ solid contribution), `low` (📄 incremental)

---

### Section 3: 🌀 Signals & Noise

对**剩余论文**进行快速分类，不需要详细分析。

分为两类：
- **[Worth Skimming]**: 有一些有趣的想法，但不够惊艳，可以快速翻翻
  - 如果有positive community signals，值得一提
- **[Pass]**: Incremental work，不需要浪费时间
  - 如果有negative community signals（如reproducibility issues），可以提及

每篇只需 1 句话理由。

HTML 格式：
```html
<div class="signals-noise">
<h2>🌀 Signals & Noise</h2>

<div class="skim-list">
<h4>📖 Worth Skimming</h4>
<ul>
<li><a href="URL">Paper Title</a> — 一句话理由（提及community signal如果relevant）</li>
</ul>
</div>

<div class="pass-list">
<h4>🚫 Pass</h4>
<ul>
<li><a href="URL">Paper Title</a> — 一句话为什么 pass</li>
</ul>
</div>

</div>
```

---

## Critical Requirements

1. **Be Ruthless**: 宁缺毋滥。如果今天没有好论文，Editor's Choice 可以是空的。
2. **Be Specific**: 不要说 "interesting approach"，要说具体 interesting 在哪里。
3. **Be Honest**: 如果你觉得一篇论文是 overhyped，直接说。
4. **Numbers Matter**: Results 要带具体数字，不要 "significantly improves"。
5. **中英文夹杂**: 专有名词（如 diffusion, CoT, RLHF, scaling law）保留英文。
6. **INTEGRATE COMMUNITY SIGNALS**: 这是最重要的升级！你必须在分析中自然融入社区信号：
   - "虽然方法简单，但Reddit上引发了关于X的大讨论"
   - "GitHub已获1k stars，说明implementation质量高"
   - "社区反馈指出reproducibility issues，需谨慎对待"

现在开始你的审阅。记住：你的读者是忙碌的researchers，他们相信你的判断。
"""
        
        return system_prompt + "\n\n---\n\n" + user_prompt

    async def generate_report(
        self, 
        papers: list[Paper],
        use_pdf_multimodal: bool = True,
    ) -> str:
        """Generate a full HTML report for the papers."""
        
        use_pdf = use_pdf_multimodal and self.client.supports_pdf_native()
        
        if use_pdf:
            html_content = await self._generate_report_with_pdfs(papers)
        else:
            html_content = await self._generate_report_with_text(papers)
        
        return self._wrap_in_template(html_content, papers)
    
    async def _generate_report_with_pdfs(self, papers: list[Paper]) -> str:
        """Generate report using PDF multimodal input."""
        papers_with_pdf = [p for p in papers if p.pdf_url]
        
        if not papers_with_pdf:
            print("   No PDFs available, using text mode")
            return await self._generate_report_with_text(papers)
        
        try:
            if self.client.is_anthropic and len(papers_with_pdf) <= 10:
                print(f"   📄 Sending {len(papers_with_pdf)} PDFs to Claude...")
                pdf_urls = [p.pdf_url for p in papers_with_pdf]
                html_content, failed_indices = await self.client.achat_with_multiple_pdfs(
                    self._build_prompt(papers, papers_with_pdf), 
                    pdf_urls, 
                    max_tokens=8000
                )
                
                if failed_indices:
                    failed_papers = [papers_with_pdf[i] for i in failed_indices]
                    print(f"   ⚠️ {len(failed_indices)} PDFs failed")
                    failed_note = self._build_failed_note(failed_papers)
                    html_content = failed_note + html_content
            else:
                print(f"   📄 Processing {len(papers_with_pdf)} PDFs individually...")
                summaries = await self._process_pdfs_individually(papers_with_pdf)
                
                prompt = self._build_prompt(papers, papers_with_pdf)
                final_prompt = f"""{prompt}

---
## Pre-Analysis (Individual PDF Summaries)
{chr(10).join(summaries)}

请基于以上预分析生成完整报告。"""
                
                html_content = await self.client.achat(
                    [{"role": "user", "content": final_prompt}],
                    max_tokens=8000
                )
        except Exception as e:
            print(f"   ⚠️ PDF processing failed: {e}, falling back to text mode")
            return await self._generate_report_with_text(papers)
        
        return html_content
    
    async def _process_pdfs_individually(self, papers: list[Paper]) -> list[str]:
        """逐个处理 PDF，使用 Senior Researcher 视角"""
        summaries = []
        
        individual_prompt = """You are a Senior Principal Researcher doing a quick paper scan.
Extract the following in 中英文夹杂 style:

1. **Authors & Affiliations**: All authors (comma-separated), main institutions
2. **The Claim**: What's the main claim/contribution? (1-2 sentences, be skeptical)
3. **The Method**: Core technical approach (2-3 sentences, specific details)
4. **The Evidence**: Key results with numbers. Any red flags? (2 sentences)
5. **Surprise Score**: 0-10, how much does this challenge conventional wisdom?
6. **One-liner Verdict**: Would you recommend this to your team? Why/why not?

Research context: """
        
        for i, paper in enumerate(papers, 1):
            print(f"      [{i}/{len(papers)}] {paper.title[:40]}...")
            try:
                summary = await self.client.achat_with_pdf(
                    individual_prompt + self.research_interests[:300],
                    pdf_url=paper.pdf_url,
                    max_tokens=800
                )
                summaries.append(f"### {paper.title}\n{paper.url}\n{summary}")
            except Exception as e:
                print(f"         ⚠️ Failed: {e}")
                summaries.append(f"### {paper.title}\n{paper.url}\n[PDF失败] Abstract: {paper.abstract[:400]}...")
        
        return summaries
    
    async def _generate_report_with_text(self, papers: list[Paper]) -> str:
        """Generate report using text-only input (abstracts only)."""
        
        papers_info = []
        for i, paper in enumerate(papers, 1):
            authors_str = ", ".join([a.name for a in paper.authors[:5]])
            if len(paper.authors) > 5:
                authors_str += " et al."
            
            # Check for research_notes
            community_signal = ""
            if hasattr(paper, 'research_notes') and paper.research_notes:
                community_signal = f"\n🔍 Community Signals: {paper.research_notes}"
            
            papers_info.append(f"""### {i}. {paper.title}
Authors: {authors_str} | URL: {paper.url}
Abstract: {paper.abstract}{community_signal}
""")
        
        prompt = f"""You are a Senior Principal Researcher at a top-tier AI lab, screening papers for your team.
You DESPISE incremental work. You hunt for Paradigm Shifts and Counter-intuitive Findings.
中英文夹杂撰写（专有名词英文）。

**IMPORTANT**: Some papers have 🔍 Community Signals. You MUST integrate them into your analysis.

## My Research Interests
{self.research_interests}

## Today's Papers ({len(papers)} papers, abstract only)
{chr(10).join(papers_info)}

---

## Output (Clean HTML, no html/head/body tags)

### 🏆 Editor's Choice (Top 1-3)
只选真正值得读的。每篇：Title (链接) + Verdict (一句话，必须提及community signal如果有) + Signal (社区热度或 N/A)

### 🌀 Quick Triage
其余论文快速分类：[Worth Skimming] 或 [Pass]，每篇 1 句话理由（提及community signal如果relevant）。

Note: 由于只有 abstract，不提供 Deep Dive。建议对 Editor's Choice 的论文下载 PDF 详读。

---

HTML 结构：
```html
<div class="editors-choice">
<h2>🏆 Editor's Choice</h2>
<div class="choice-item">
<h3><a href="URL">Title</a></h3>
<p class="verdict"><b>Verdict:</b> ... (integrate community signal)</p>
<p class="signal"><b>Signal:</b> ...</p>
</div>
</div>

<div class="signals-noise">
<h2>🌀 Quick Triage</h2>
<div class="skim-list"><h4>📖 Worth Skimming</h4><ul><li>...</li></ul></div>
<div class="pass-list"><h4>🚫 Pass</h4><ul><li>...</li></ul></div>
</div>
```

Be ruthless. 宁缺毋滥。INTEGRATE COMMUNITY SIGNALS naturally into your analysis.
"""
        
        messages = [{"role": "user", "content": prompt}]
        return await self.client.achat(messages, max_tokens=6000)
    
    def _build_failed_note(self, failed_papers: list[Paper]) -> str:
        """构建 PDF 下载失败的提示"""
        titles = ", ".join([f'<a href="{p.url}">{p.title[:30]}...</a>' for p in failed_papers[:3]])
        if len(failed_papers) > 3:
            titles += f" 等 {len(failed_papers)} 篇"
        return f'<div class="warning">⚠️ PDF 下载失败（已用摘要替代）: {titles}</div>'
    
    def _wrap_in_template(self, content: str, papers: list[Paper]) -> str:
        """Wrap content in a refined HTML template with MathJax support."""
        today = datetime.now().strftime("%Y-%m-%d")
        today_cn = datetime.now().strftime("%m月%d日")
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.now().weekday()]
        
        return f"""<!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Paper Digest {today}</title>
        
        <!-- MathJax for LaTeX rendering -->
        <script>
            MathJax = {{
                tex: {{
                    inlineMath: [['$', '$'], ['\\(', '\\)']],
                    displayMath: [['$$', '$$'], ['\\[', '\\]']],
                    processEscapes: true
                }},
                options: {{
                    skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre']
                }}
            }};
        </script>
        <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>
        
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
                font-size: 15px;
                line-height: 1.65;
                color: #1a1a1a;
                background: #f0f0f0;
                padding: 12px;
            }}
            
            .container {{
                max-width: 920px;
                margin: 0 auto;
                background: #fff;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }}
            
            .header {{
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
            
            .skim-list, .pass-list {{
                margin-bottom: 12px;
            }}
            
            .skim-list h4 {{ color: #28a745; }}
            .pass-list h4 {{ color: #6c757d; }}
            
            .skim-list ul, .pass-list ul {{
                padding-left: 20px;
                margin: 0;
            }}
            
            .skim-list li, .pass-list li {{
                font-size: 0.88em;
                color: #555;
                padding: 3px 0;
            }}
            
            .skim-list a {{ color: #28a745; }}
            .pass-list a {{ color: #6c757d; }}
            
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
                .editors-choice, .signals-noise {{ padding: 12px 14px; }}
                .choice-item {{ padding: 10px 12px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📚 Paper Digest</h1>
                <div class="meta">{today_cn} {weekday} · {len(papers)} papers reviewed</div>
                <div class="persona">Curated by Senior Principal Researcher · No fluff, no hype</div>
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
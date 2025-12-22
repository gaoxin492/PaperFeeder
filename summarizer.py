"""
Paper summarization using any LLM.
Generates daily digest with summaries and insights.
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
        pdf_max_pages: int = 10,  # PDF最大页数（0表示不限制，默认10页）
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
        """构建精简但有深度的 prompt"""
        
        failed_pdf_set = set(failed_pdf_papers) if failed_pdf_papers else set()
        
        papers_info = []
        for i, paper in enumerate(papers, 1):
            authors_str = ", ".join([a.name for a in paper.authors[:3]])
            if len(paper.authors) > 3:
                authors_str += " et al."
            
            has_pdf = papers_with_pdf and paper in papers_with_pdf
            is_failed = paper in failed_pdf_set
            
            if is_failed:
                pdf_note = " [⚠️ PDF失败]"
            elif has_pdf:
                pdf_note = " [PDF]"
            else:
                pdf_note = ""
            papers_info.append(f"{i}. {paper.title} - {authors_str}{pdf_note}\n   URL: {paper.url}")
        
        pdf_context = ""
        if papers_with_pdf:
            successful_count = len(papers_with_pdf) - len(failed_pdf_set)
            pdf_context = f"\n\n📄 已提供 {successful_count} 篇 PDF 全文。"
            if failed_pdf_set:
                pdf_context += f"（{len(failed_pdf_set)} 篇失败，基于摘要）"
        
        return f"""你是 AI 研究助手。用中英文夹杂撰写（专有名词英文，其他中文）。

## 我的研究方向
{self.research_interests}

## 今日论文（{len(papers)} 篇）
{chr(10).join(papers_info)}{pdf_context}

---

## 输出格式

### 🔥 今日必读（Top 3）
选最相关的 3 篇，每篇 1 句话说明理由。

### 📄 论文详解
每篇论文包含：

**👥 Authors** (1行)
直接使用提供的作者和单位：格式 "作者1, 作者2, ... 单位1, 单位2, ..."，最多 20 人

**🎯 Problem** (1-2句)
解决什么问题？现有方法痛点？

**💡 Key Idea** (3-5句)
核心思路 + 具体方法设计 + 为什么 work

**📊 Results** (2-3句)
主要结果（具体数字）+ baseline 对比

**🤔 Takeaway** (1句)
对我研究的具体价值

### 💡 今日启发（简短）
- **趋势**: 1-2句跨论文洞察
- **行动**: 值得复现/引用/跟进的点（每类1个）
- **问题**: 1个值得思考的开放问题

---

## 要求
1. 每篇论文总计 150 字左右，要有技术深度但不啰嗦
2. 今日启发控制在 100 字以内
3. 输出 clean HTML（不要 html/head/body 标签）
4. 避免空话套话，多用具体方法名和数字

## HTML 格式
```html
<div class="must-read">
<h2>🔥 今日必读</h2>
<ol>
<li><a href="URL">标题</a> — 理由</li>
</ol>
</div>

<div class="paper">
<h3 class="paper-title"><span class="badge high">🔥</span><a href="URL">标题</a></h3>
<div class="paper-body">
<p class="authors">👥 作者1, 作者2, 作者3, ...<br>📍 Institutions: 单位1, 单位2</p>
<p><b>🎯 Problem:</b> ...</p>
<p><b>💡 Key Idea:</b> ...</p>
<p><b>📊 Results:</b> ...</p>
<p><b>🤔 Takeaway:</b> ...</p>
</div>
</div>

<div class="insights">
<h2>💡 今日启发</h2>
<p><b>趋势:</b> ...</p>
<p><b>行动:</b> 🔬复现: ... | 📚引用: ... | 🚀跟进: ...</p>
<p><b>问题:</b> ...</p>
</div>
```

badge: high (🔥), medium (⭐), low (📄)
"""

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
## 预分析
{chr(10).join(summaries)}

请生成完整报告。"""
                
                html_content = await self.client.achat(
                    [{"role": "user", "content": final_prompt}],
                    max_tokens=8000
                )
        except Exception as e:
            print(f"   ⚠️ PDF processing failed: {e}, falling back to text mode")
            return await self._generate_report_with_text(papers)
        
        return html_content
    
    async def _process_pdfs_individually(self, papers: list[Paper]) -> list[str]:
        """逐个处理 PDF"""
        summaries = []
        
        for i, paper in enumerate(papers, 1):
            print(f"      [{i}/{len(papers)}] {paper.title[:40]}...")
            try:
                summary = await self.client.achat_with_pdf(
                    f"""中英文夹杂分析这篇论文：
1. Authors: 所有作者姓名（逗号分隔）
2. Institutions: 主要单位（学校/机构/公司，去重）
3. Problem (1-2句)
4. Key Idea + Method (3-4句)
5. Results (2句，具体数字)
6. Insight (1句)

研究背景：{self.research_interests[:200]}""",
                    pdf_url=paper.pdf_url,
                    max_tokens=700
                )
                summaries.append(f"### {paper.title}\n{paper.url}\n{summary}")
            except Exception as e:
                print(f"         ⚠️ Failed: {e}")
                summaries.append(f"### {paper.title}\n{paper.url}\n[PDF失败] Abstract: {paper.abstract[:400]}...")
        
        return summaries
    
    async def _generate_report_with_text(self, papers: list[Paper]) -> str:
        """Generate report using text-only input."""
        
        papers_info = []
        for i, paper in enumerate(papers, 1):
            authors_str = ", ".join([a.name for a in paper.authors[:3]])
            if len(paper.authors) > 3:
                authors_str += " et al."
            
            papers_info.append(f"""### {i}. {paper.title}
Authors: {authors_str} | URL: {paper.url}
Abstract: {paper.abstract}
""")
        
        prompt = f"""你是 AI 研究助手。用中英文夹杂撰写。

## 我的研究方向
{self.research_interests}

## 今日论文（{len(papers)} 篇）
{chr(10).join(papers_info)}

---

## 输出格式（基于 abstract 分析）

### 🔥 今日必读（Top 3）
最相关的 3 篇，每篇 1 句话理由。

### 📄 论文详解
每篇：Problem (1-2句) + Key Idea (2-3句) + Results (1-2句，有数字就提取) + Takeaway (1句)

### 💡 今日启发
趋势 (1句) + 行动 (复现/引用/跟进各1个) + 问题 (1个)

---

输出 clean HTML，不要 html/head/body 标签。
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
        """Wrap content in a compact, mobile-friendly HTML template."""
        today = datetime.now().strftime("%Y-%m-%d")
        today_cn = datetime.now().strftime("%m月%d日")
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.now().weekday()]
        
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paper Digest {today}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
            font-size: 15px;
            line-height: 1.6;
            color: #1a1a1a;
            background: #f5f5f5;
            padding: 8px;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: #fff;
            border-radius: 8px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: #fff;
            padding: 16px 20px;
            text-align: center;
            border-radius: 8px 8px 0 0;
        }}
        
        .header h1 {{ font-size: 1.3em; font-weight: 600; }}
        .header .meta {{ opacity: 0.9; font-size: 0.9em; margin-top: 2px; }}
        
        .content {{ padding: 16px 20px; }}
        
        h2 {{
            font-size: 1.05em;
            font-weight: 600;
            color: #333;
            margin: 20px 0 10px 0;
            padding-bottom: 6px;
            border-bottom: 2px solid #eee;
        }}
        
        h3 {{ font-size: 1em; color: #1a1a1a; }}
        
        /* 今日必读 */
        .must-read {{
            background: #fff8f8;
            border: 1px solid #ffebeb;
            border-radius: 6px;
            padding: 12px 16px;
            margin-bottom: 16px;
        }}
        
        .must-read h2 {{
            color: #d63031;
            margin: 0 0 8px 0;
            padding: 0;
            border: none;
            font-size: 1em;
        }}
        
        .must-read ol {{ padding-left: 18px; margin: 0; }}
        .must-read li {{ padding: 4px 0; font-size: 0.92em; }}
        .must-read a {{ color: #d63031; font-weight: 500; text-decoration: none; }}
        .must-read a:hover {{ text-decoration: underline; }}
        
        /* 论文卡片 */
        .paper {{
            padding: 14px 16px;
            margin-bottom: 12px;
            background: #fafafa;
            border-radius: 6px;
            border-left: 3px solid #667eea;
        }}
        
        .paper-title {{
            font-size: 0.98em;
            font-weight: 600;
            margin-bottom: 10px;
            line-height: 1.4;
        }}
        
        .paper-title a {{ color: #1a1a1a; text-decoration: none; }}
        .paper-title a:hover {{ color: #667eea; }}
        
        .badge {{
            display: inline-block;
            padding: 1px 6px;
            border-radius: 10px;
            font-size: 0.7em;
            margin-right: 6px;
            vertical-align: middle;
        }}
        
        .badge.high {{ background: #ffe0e0; color: #c0392b; }}
        .badge.medium {{ background: #fff3cd; color: #b7791f; }}
        .badge.low {{ background: #e8e8e8; color: #666; }}
        
        .paper-body {{ font-size: 0.9em; color: #444; }}
        .paper-body p {{ margin-bottom: 8px; }}
        .paper-body b {{ color: #222; }}
        .paper-body .authors {{ color: #666; font-size: 0.85em; margin-bottom: 10px; }}
        
        /* 今日启发 */
        .insights {{
            background: #f0fff4;
            border: 1px solid #c6f6d5;
            border-radius: 6px;
            padding: 12px 16px;
            margin-top: 16px;
        }}
        
        .insights h2 {{
            color: #276749;
            margin: 0 0 10px 0;
            padding: 0;
            border: none;
            font-size: 1em;
        }}
        
        .insights p {{
            font-size: 0.9em;
            color: #2d3748;
            margin-bottom: 6px;
        }}
        
        .insights b {{ color: #276749; }}
        
        /* 警告 */
        .warning {{
            background: #fffaf0;
            border: 1px solid #ed8936;
            border-radius: 6px;
            padding: 10px 14px;
            margin-bottom: 12px;
            font-size: 0.85em;
            color: #c05621;
        }}
        
        .warning a {{ color: #c05621; }}
        
        .footer {{
            text-align: center;
            padding: 12px;
            font-size: 0.75em;
            color: #999;
            border-top: 1px solid #eee;
        }}
        
        a {{ color: #667eea; }}
        
        @media (max-width: 600px) {{
            body {{ padding: 4px; font-size: 14px; }}
            .content {{ padding: 12px 14px; }}
            .header {{ padding: 12px 14px; }}
            .paper {{ padding: 12px 14px; }}
            .must-read, .insights {{ padding: 10px 12px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 Daily Paper Digest</h1>
            <div class="meta">{today_cn} {weekday} · {len(papers)} 篇</div>
        </div>
        
        <div class="content">
            {content}
        </div>
        
        <div class="footer">
            Paper Assistant · {self._get_unique_keywords(papers)}
        </div>
    </div>
</body>
</html>"""
    
    def _get_unique_keywords(self, papers: list[Paper]) -> str:
        """Get unique matched keywords."""
        keywords = set()
        for paper in papers:
            keywords.update(paper.matched_keywords)
        return ", ".join(sorted(keywords)[:8]) if keywords else ""


# Backward compatibility
ClaudeSummarizer = PaperSummarizer

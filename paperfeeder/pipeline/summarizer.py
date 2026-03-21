"""
Paper summarization using any LLM.
"""

from __future__ import annotations

from datetime import datetime
import re

from paperfeeder.models import Paper
from paperfeeder.chat import LLMClient
from paperfeeder.pipeline.prompt_templates import get_summary_language_pack


class PaperSummarizer:
    """Generate paper summaries and insights using any LLM."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        research_interests: str = "",
        prompt_addon: str = "",
        prompt_language: str = "zh-CN",
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
            pdf_max_pages=pdf_max_pages,
        )
        self.research_interests = research_interests
        self.prompt_addon = prompt_addon.strip()
        self.language_pack = get_summary_language_pack(prompt_language)

    @staticmethod
    def _strip_skip_sections(content: str) -> str:
        if not content:
            return content

        patterns = (
            r"<section\b[^>]*>\s*<(?:h1|h2|h3|h4|p)\b[^>]*>\s*(?:[^<]*?)?(?:⏭|跳过|未入选|skip(?:ped)?|rejected|not selected)[^<]*</(?:h1|h2|h3|h4|p)>.*?</section>",
            r"<(?:h1|h2|h3|h4)\b[^>]*>\s*(?:[^<]*?)?(?:⏭|跳过|未入选|skip(?:ped)?|rejected|not selected)[^<]*</(?:h1|h2|h3|h4)>\s*(?:<(?:p|ul|ol|div)\b[^>]*>.*?</(?:p|ul|ol|div)>\s*){0,6}",
        )

        cleaned = content
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        return cleaned.strip()

    @staticmethod
    def _strip_raw_separators(content: str) -> str:
        if not content:
            return content

        cleaned = re.sub(r"<p\b[^>]*>\s*(?:---+|___+)\s*</p>", "", content, flags=re.IGNORECASE)
        cleaned = re.sub(r"<div\b[^>]*>\s*(?:---+|___+)\s*</div>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"(^|\n)\s*(?:---+|___+)\s*(?=\n|$)", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _split_badge_and_title_lines(content: str) -> str:
        if not content:
            return content

        cleaned = re.sub(
            r"(</span>)\s*(<a\b[^>]*>)",
            r"\1<br>\2",
            content,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(</span>)\s*(<strong\b[^>]*>)",
            r"\1<br>\2",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(</span>)\s*(<h[1-4]\b[^>]*>)",
            r"\1\n\2",
            cleaned,
            flags=re.IGNORECASE,
        )
        return cleaned

    def _build_prompt(
        self,
        papers: list[Paper],
        papers_with_pdf: list[Paper] = None,
        failed_pdf_papers: list[Paper] = None,
        blog_posts: list[Paper] = None,
    ) -> str:
        failed_pdf_set = set(failed_pdf_papers) if failed_pdf_papers else set()
        blog_posts = blog_posts or []

        papers_info = []
        for i, paper in enumerate(papers, 1):
            authors_str = ", ".join([author.name for author in paper.authors[:5]])
            if len(paper.authors) > 5:
                authors_str += " et al."

            has_pdf = papers_with_pdf and paper in papers_with_pdf
            is_failed = paper in failed_pdf_set
            if is_failed:
                pdf_note = " [PDF failed]"
            elif has_pdf:
                pdf_note = " [PDF]"
            else:
                pdf_note = ""

            community_signal = ""
            if hasattr(paper, "research_notes") and paper.research_notes:
                community_signal = f"\n   Community Signals: {paper.research_notes}"

            papers_info.append(
                f"{i}. {paper.title}{pdf_note}\n"
                f"   Authors: {authors_str}\n"
                f"   URL: {paper.url}"
                f"{community_signal}"
            )

        blog_info = []
        if blog_posts:
            for i, post in enumerate(blog_posts, 1):
                source = getattr(post, "blog_source", "Unknown")
                title = post.title[7:] if post.title.startswith("[Blog] ") else post.title
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
            pdf_context = f"\n\n{successful_count} PDFs provided for deep analysis."
            if failed_pdf_set:
                pdf_context += f" ({len(failed_pdf_set)} failed, using abstract only)"

        system_prompt = self.language_pack.system_prompt

        if self.prompt_addon:
            system_prompt += f"\n\n{self.language_pack.additional_guidance_heading}\n{self.prompt_addon}"

        papers_section = ""
        if papers:
            papers_section = f"""
    {self.language_pack.papers_section_heading.format(count=len(papers))}
{chr(10).join(papers_info)}{pdf_context}
"""

        blogs_section = ""
        if blog_posts:
            blogs_section = f"""
    {self.language_pack.blogs_section_heading.format(count=len(blog_posts))}
    {self.language_pack.blogs_section_intro}

{chr(10).join(blog_info)}
"""

        requirements = "\n".join(
            f"{i}. {line}" for i, line in enumerate(self.language_pack.task_requirements, 1)
        )

        user_prompt = f"""{self.language_pack.my_research_interests_heading}
{self.research_interests}
{blogs_section}{papers_section}
---

    {self.language_pack.task_heading}

    {self.language_pack.task_intro}

Critical requirements:
    {requirements}
"""

        return {"system": system_prompt, "user": user_prompt}

    async def generate_report(
        self,
        papers: list[Paper],
        use_pdf_multimodal: bool = True,
        blog_posts: list[Paper] = None,
    ) -> str:
        if not papers and not blog_posts:
            return self._wrap_html(self.language_pack.html_empty_state, [], blog_posts)

        actual_papers = []
        actual_blogs = list(blog_posts) if blog_posts else []
        for paper in papers:
            if getattr(paper, "is_blog", False):
                actual_blogs.append(paper)
            else:
                actual_papers.append(paper)

        seen_urls = set()
        unique_blogs = []
        for blog in actual_blogs:
            if blog.url not in seen_urls:
                seen_urls.add(blog.url)
                unique_blogs.append(blog)
        actual_blogs = unique_blogs

        papers_with_pdf = []
        failed_pdf_papers = []
        if use_pdf_multimodal and actual_papers:
            print(f"   Processing {len(actual_papers)} PDFs individually...")
            for i, paper in enumerate(actual_papers, 1):
                print(f"      [{i}/{len(actual_papers)}] {paper.title[:40]}...")
                if not getattr(paper, "pdf_url", None):
                    failed_pdf_papers.append(paper)
                    paper._pdf_base64 = None
                    print("      No pdf_url, fallback to abstract-only")
                    continue
                pdf_content = await self.client._url_to_base64_async(
                    paper.pdf_url,
                    save_debug=getattr(self.client, "debug_save_pdfs", False),
                    debug_dir=getattr(self.client, "debug_pdf_dir", "debug_pdfs"),
                    max_pages=getattr(self.client, "pdf_max_pages", 10),
                )
                if pdf_content:
                    paper._pdf_base64 = pdf_content
                    papers_with_pdf.append(paper)
                else:
                    failed_pdf_papers.append(paper)
                    paper._pdf_base64 = None

        prompts = self._build_prompt(actual_papers, papers_with_pdf, failed_pdf_papers, blog_posts=actual_blogs)
        messages = [{"role": "system", "content": prompts["system"]}]

        user_content = []
        for paper in papers_with_pdf:
            if paper not in failed_pdf_papers and hasattr(paper, "_pdf_base64") and paper._pdf_base64:
                user_content.append(
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": paper._pdf_base64,
                        },
                        "cache_control": {"type": "ephemeral"},
                    }
                )
        user_content.append({"type": "text", "text": prompts["user"]})
        messages.append({"role": "user", "content": user_content})

        try:
            content = await self.client.achat(messages, max_tokens=8000)
            content = self._strip_skip_sections(content)
            content = self._strip_raw_separators(content)
            content = self._split_badge_and_title_lines(content)
            all_items = actual_papers + actual_blogs
            return self._wrap_html(content, all_items, actual_blogs)
        except Exception as exc:
            error_msg = f"<p class='error'>Error generating report: {str(exc)}</p>"
            return self._wrap_html(error_msg, actual_papers, actual_blogs)

    def _wrap_html(self, content: str, papers: list[Paper], blog_posts: list[Paper] = None) -> str:
        pack = self.language_pack
        today = datetime.now()
        today_label = today.strftime(pack.date_format)
        weekday = pack.weekdays[today.weekday()]
        paper_count = len([paper for paper in papers if not getattr(paper, "is_blog", False)])
        blog_count = len(blog_posts) if blog_posts else 0
        meta_str = pack.reviewed_summary(paper_count, blog_count)

        return f"""<!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{pack.html_title} - {today.strftime('%Y-%m-%d')}</title>
        <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <style>
            :root {{ color-scheme: light; }}
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                line-height: 1.7;
                color: #1e293b;
                background: linear-gradient(180deg, #edf5fd 0%, #eff6ff 48%, #e2e8f0 100%);
                padding: 10px 2px 14px;
                padding:
                    max(10px, calc(10px + env(safe-area-inset-top)))
                    max(2px, calc(2px + env(safe-area-inset-right)))
                    max(14px, calc(14px + env(safe-area-inset-bottom)))
                    max(2px, calc(2px + env(safe-area-inset-left)));
                font-size: clamp(15px, 2.8vw, 16px);
            }}
            .container {{
                max-width: min(48rem, 100%);
                margin: 0 auto;
                background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
                border-radius: 24px;
                box-shadow: 0 12px 32px rgba(37, 99, 235, 0.08);
                border: 1px solid rgba(191, 219, 254, 0.95);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #eaf6ff 0%, #dff1ff 55%, #dbeafe 100%);
                color: #0c4a6e;
                padding: 14px 8px 12px;
                text-align: center;
                border-bottom: 1px solid rgba(125, 211, 252, 0.65);
            }}
            .header h1 {{ font-size: 1.95rem; font-weight: 800; letter-spacing: -0.03em; color: #0a6aa1; text-shadow: 0 1px 0 rgba(255,255,255,0.55); }}
            .header .meta {{ margin-top: 10px; font-size: 0.98rem; font-weight: 500; color: #0e7490; line-height: 1.55; }}
            .header .persona {{ margin-top: 10px; font-size: 0.82rem; color: #64748b; line-height: 1.5; }}
            .content {{
                padding: 12px 4px 16px;
                color: #1e293b;
            }}
            .content > * + * {{ margin-top: 18px; }}
            .content section {{
                background: #ffffff;
                border: 1px solid #dbeafe;
                border-radius: 18px;
                padding: 14px 12px;
                box-shadow: 0 4px 14px rgba(148, 163, 184, 0.08);
            }}
            .content section:first-of-type {{
                padding: 16px 18px 18px;
            }}
            .content section + section {{ margin-top: 18px; }}
            .content h2 {{
                color: #1e293b;
                font-size: 1.1rem;
                font-weight: 800;
                line-height: 1.3;
                margin: 24px 0 14px;
                padding: 0 0 10px;
                border-bottom: 3px solid #60a5fa;
            }}
            .content h2:first-child {{ margin-top: 0; }}
            .content h3 {{
                color: #0f172a;
                font-size: 1rem;
                font-weight: 800;
                line-height: 1.4;
                margin: 16px 0 10px;
            }}
            .content p {{ margin: 0 0 12px; color: #475569; }}
            .content ul, .content ol {{ margin: 0 0 16px 1.35em; color: #334155; }}
            .content li + li {{ margin-top: 10px; }}
            .content strong {{ color: #1e293b; }}
            .content a {{ color: #2563eb; text-decoration: none; font-weight: 700; }}
            .content blockquote {{
                margin: 18px 0;
                padding: 16px 18px;
                background: linear-gradient(180deg, #eff6ff 0%, #f8fbff 100%);
                border: 1px solid #cfe3ff;
                border-radius: 16px;
            }}
            .footer {{ text-align: center; padding: 12px 16px; font-size: 0.72rem; color: #64748b; border-top: 1px solid #dbeafe; background: linear-gradient(180deg, #f8fbff 0%, #f8fafc 100%); }}
            @media (max-width: 640px) {{
                body {{
                    padding: 8px 1px 12px;
                    padding:
                        max(8px, calc(8px + env(safe-area-inset-top)))
                        max(1px, calc(1px + env(safe-area-inset-right)))
                        max(12px, calc(12px + env(safe-area-inset-bottom)))
                        max(1px, calc(1px + env(safe-area-inset-left)));
                }}
                .container {{ border-radius: 20px; }}
                .header {{ padding: 12px 6px 10px; }}
                .header h1 {{ font-size: 1.75rem; }}
                .content {{ padding: 10px 3px 14px; }}
                .content section {{ padding: 12px 10px; border-radius: 16px; }}
                .content section:first-of-type {{ padding: 14px 14px 16px; }}
                .content h2 {{ font-size: 0.98rem; margin: 26px 0 16px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{pack.header_title}</h1>
                <div class="meta">{today_label} {weekday} · {meta_str}</div>
                <div class="persona">{pack.persona_label}</div>
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
        keywords = set()
        for paper in papers:
            if hasattr(paper, "matched_keywords"):
                keywords.update(paper.matched_keywords)
        return ", ".join(sorted(keywords)[:8]) if keywords else self.language_pack.footer_fallback


ClaudeSummarizer = PaperSummarizer

"""
Paper summarization using any LLM.
"""

from __future__ import annotations

import html
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

    @staticmethod
    def _strip_secondary_heading_counts(content: str) -> str:
        if not content:
            return content

        cleaned = re.sub(
            r"(值得知道但暂不主推)\s*[（\(][^）\)]{0,20}[）\)]",
            r"\1",
            content,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(Worth Knowing, Not Main Picks)\s*[（\(][^）\)]{0,20}[）\)]",
            r"\1",
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
            content = self._strip_secondary_heading_counts(content)
            content = self._split_badge_and_title_lines(content)
            all_items = actual_papers + actual_blogs
            return self._wrap_html(content, all_items, actual_blogs)
        except Exception as exc:
            error_msg = f"<p class='error'>Error generating report: {str(exc)}</p>"
            return self._wrap_html(error_msg, actual_papers, actual_blogs)

    def rewrap_existing_report_html(self, existing_html: str) -> str:
        extracted_html = self._extract_report_payload_html(existing_html)
        content = self._extract_existing_content(extracted_html)
        content = self._wrap_lead_summary_block(content)
        content = self._strip_existing_section_marks(content)
        content = self._decorate_section_headings(content)
        content = self._restyle_feedback_layout(content)
        content = self._inline_title_links(content)
        title_text = self._extract_first_match(extracted_html, r"<h1[^>]*>(.*?)</h1>") or self.language_pack.header_title
        meta_text = self._extract_first_match(extracted_html, r'<div class="meta">(.*?)</div>')
        persona_text = self._normalize_persona_text(
            self._extract_first_match(extracted_html, r'<div class="persona">(.*?)</div>')
        )
        footer_text = self._extract_first_match(extracted_html, r'<div class="footer">(.*?)</div>')
        return self._render_wrapped_html(
            content=content,
            header_title=title_text,
            meta_text=meta_text or self.language_pack.reviewed_summary(0, 0),
            persona_text=persona_text or self._normalize_persona_text(self.language_pack.persona_label),
            footer_text=footer_text or f"PaperFeeder · {self.language_pack.footer_fallback}",
        )

    def _wrap_html(self, content: str, papers: list[Paper], blog_posts: list[Paper] = None) -> str:
        pack = self.language_pack
        today = datetime.now()
        today_label = today.strftime(pack.date_format)
        weekday = pack.weekdays[today.weekday()]
        paper_count = len([paper for paper in papers if not getattr(paper, "is_blog", False)])
        blog_count = len(blog_posts) if blog_posts else 0
        meta_str = pack.reviewed_summary(paper_count, blog_count)
        footer_text = f"PaperFeeder · {self._get_unique_keywords(papers)}"

        return self._render_wrapped_html(
            content=self._inline_title_links(
                self._restyle_feedback_layout(
                    self._decorate_section_headings(
                        self._strip_existing_section_marks(self._wrap_lead_summary_block(content))
                    )
                )
            ),
            header_title=pack.header_title,
            meta_text=f"{today_label} {weekday} · {meta_str}",
            persona_text=self._normalize_persona_text(pack.persona_label),
            footer_text=footer_text,
        )

    def _render_wrapped_html(
        self,
        *,
        content: str,
        header_title: str,
        meta_text: str,
        persona_text: str,
        footer_text: str,
    ) -> str:
        pack = self.language_pack
        today = datetime.now()
        feedback_note = self._feedback_note_text()

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
                background:
                    radial-gradient(circle at top left, rgba(191, 219, 254, 0.75), transparent 34%),
                    radial-gradient(circle at top right, rgba(186, 230, 253, 0.55), transparent 28%),
                    linear-gradient(180deg, #eef6ff 0%, #f3f8ff 46%, #e7eef7 100%);
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
                background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, #f8fbff 100%);
                border-radius: 28px;
                box-shadow: 0 18px 44px rgba(37, 99, 235, 0.10);
                border: 1px solid rgba(186, 230, 253, 0.95);
                overflow: hidden;
            }}
            .header {{
                background:
                    radial-gradient(circle at top, rgba(255,255,255,0.72), transparent 54%),
                    linear-gradient(135deg, #eaf6ff 0%, #dff1ff 52%, #d7ebff 100%);
                color: #0c4a6e;
                padding: 18px 10px 14px;
                text-align: center;
                border-bottom: 1px solid rgba(125, 211, 252, 0.65);
            }}
            .header h1 {{ font-size: 2.02rem; font-weight: 850; letter-spacing: -0.04em; color: #0a6aa1; text-shadow: 0 1px 0 rgba(255,255,255,0.6); }}
            .header .meta {{ margin-top: 12px; font-size: 1rem; font-weight: 600; color: #0e7490; line-height: 1.5; }}
            .header .persona {{ margin-top: 12px; font-size: 0.82rem; color: #64748b; line-height: 1.5; }}
            .content {{
                padding: 14px 6px 18px;
                color: #1e293b;
            }}
            .content > * + * {{ margin-top: 18px; }}
            .section-mark {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 1.72em;
                height: 1.72em;
                margin-right: 0.48em;
                border-radius: 999px;
                font-size: 0.9em;
                line-height: 1;
                vertical-align: -0.18em;
                background: linear-gradient(180deg, #e0f2fe 0%, #dbeafe 100%);
                box-shadow: inset 0 1px 0 rgba(255,255,255,0.85), 0 4px 10px rgba(96, 165, 250, 0.15);
            }}
            .section-mark.summary {{
                background: linear-gradient(180deg, #dbeafe 0%, #bfdbfe 100%);
            }}
            .section-mark.blog {{
                background: linear-gradient(180deg, #e0f2fe 0%, #bae6fd 100%);
            }}
            .section-mark.paper {{
                background: linear-gradient(180deg, #dcfce7 0%, #bbf7d0 100%);
            }}
            .section-mark.judgment {{
                background: linear-gradient(180deg, #ede9fe 0%, #ddd6fe 100%);
            }}
            .section-mark.secondary {{
                background: linear-gradient(180deg, #fef3c7 0%, #fde68a 100%);
            }}
            .content .lead-summary {{
                background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
                border: 1px solid #cfe3ff;
                border-radius: 22px;
                box-shadow: 0 10px 24px rgba(148, 163, 184, 0.10);
                padding: 24px 30px 26px;
                margin: 4px 10px 24px;
            }}
            .content .lead-summary > * + * {{ margin-top: 14px; }}
            .content .lead-summary h2 {{ margin-top: 0; }}
            .content .lead-summary p:last-child {{ margin-bottom: 0; }}
            .content section {{
                background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
                border: 1px solid #d9eafe;
                border-radius: 20px;
                padding: 16px 14px;
                box-shadow: 0 8px 18px rgba(148, 163, 184, 0.09);
            }}
            .content section:first-of-type {{
                padding: 20px 34px 22px;
            }}
            .content section + section {{ margin-top: 18px; }}
            .content h2 {{
                color: #1e293b;
                font-size: 1.12rem;
                font-weight: 800;
                line-height: 1.3;
                margin: 28px 0 16px;
                padding: 0 0 12px;
                border-bottom: 2px solid rgba(96, 165, 250, 0.36);
            }}
            .content h2:first-child {{ margin-top: 0; }}
            .content h3 {{
                color: #0f172a;
                font-size: 1.02rem;
                font-weight: 800;
                line-height: 1.4;
                margin: 16px 0 10px;
            }}
            .content h3 a, .pf-brief-title a {{ color: inherit; text-decoration: none; font-weight: inherit; }}
            .content h3 a:hover, .pf-brief-title a:hover {{ color: #1d4ed8; }}
            .content p {{ margin: 0 0 12px; color: #475569; font-size: 1.02rem; }}
            .content ul, .content ol {{ margin: 0 0 16px 1.35em; color: #334155; }}
            .content li + li {{ margin-top: 10px; }}
            .content strong {{ color: #1e293b; }}
            .content a {{ color: #2563eb; text-decoration: none; font-weight: 700; }}
            .pf-brief-link, .pf-brief-comment {{ margin-top: 10px; }}
            .pf-feedback-row, .pf-brief-title, .pf-brief-link, .pf-brief-comment {{ display: block; }}
            .pf-brief-link {{ font-size: 0.9rem; color: #516072; }}
            .pf-brief-link a {{ display: inline-block; font-size: 0.92rem; }}
            .content section h3 + div a {{ display: inline-block; margin-top: 6px; }}
            .pf-feedback-row {{
                margin-top: 12px;
                padding: 10px 12px;
                background: linear-gradient(180deg, #f8fbff 0%, #eef6ff 100%);
                border: 1px solid #d7e9ff;
                border-radius: 14px;
            }}
            .pf-feedback-actions {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
            .pf-feedback-btn {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-height: 34px;
                width: 100%;
                padding: 6px 10px;
                border-radius: 999px;
                font-size: 0.82rem;
                font-weight: 800;
                line-height: 1.2;
                border: 1px solid transparent;
                box-shadow: inset 0 1px 0 rgba(255,255,255,0.7);
                white-space: nowrap;
            }}
            .pf-feedback-btn.positive {{ background: #dcfce7; color: #166534; border-color: #bbf7d0; }}
            .pf-feedback-btn.negative {{ background: #fee2e2; color: #b91c1c; border-color: #fecaca; }}
            .pf-feedback-btn.undecided {{ background: #fef3c7; color: #92400e; border-color: #fde68a; }}
            .pf-brief-item {{ list-style: none; margin-left: 0; padding-left: 0; }}
            .pf-brief-item + .pf-brief-item {{ margin-top: 16px; }}
            .pf-brief-title strong {{ font-size: 1rem; color: #0f172a; }}
            .pf-brief-comment {{ color: #334155; line-height: 1.8; }}
            .content blockquote {{
                margin: 18px 0;
                padding: 16px 18px;
                background: linear-gradient(180deg, #eff6ff 0%, #f8fbff 100%);
                border: 1px solid #cfe3ff;
                border-radius: 16px;
            }}
            .footer {{ text-align: center; padding: 14px 18px; font-size: 0.72rem; color: #64748b; border-top: 1px solid #dbeafe; background: linear-gradient(180deg, #f8fbff 0%, #f8fafc 100%); }}
            .footer-note {{ margin-top: 7px; font-size: 0.72rem; line-height: 1.55; color: #7c8aa0; max-width: 44rem; margin-left: auto; margin-right: auto; }}
            @media (max-width: 640px) {{
                body {{
                    padding: 8px 1px 12px;
                    padding:
                        max(8px, calc(8px + env(safe-area-inset-top)))
                        max(1px, calc(1px + env(safe-area-inset-right)))
                        max(12px, calc(12px + env(safe-area-inset-bottom)))
                        max(1px, calc(1px + env(safe-area-inset-left)));
                }}
                .container {{ border-radius: 22px; }}
                .header {{ padding: 14px 8px 12px; }}
                .header h1 {{ font-size: 1.78rem; }}
                .content {{ padding: 10px 3px 14px; }}
                .section-mark {{ width: 1.6em; height: 1.6em; margin-right: 0.42em; }}
                .content .lead-summary {{ padding: 18px 20px 20px; margin: 2px 6px 20px; border-radius: 18px; }}
                .content section {{ padding: 12px 10px; border-radius: 16px; }}
                .content section:first-of-type {{ padding: 18px 22px 20px; }}
                .content h2 {{ font-size: 0.98rem; margin: 26px 0 16px; }}
                .pf-feedback-row {{ padding: 9px 10px; }}
                .pf-feedback-actions {{ gap: 6px; }}
                .pf-feedback-btn {{ min-height: 32px; padding: 6px 8px; font-size: 0.76rem; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{header_title}</h1>
                <div class="meta">{meta_text}</div>
                <div class="persona">{persona_text}</div>
            </div>
            <div class="content">
                {content}
            </div>
            <div class="footer">
                {footer_text}
                <div class="footer-note">{feedback_note}</div>
            </div>
        </div>
    </body>
    </html>"""

    @staticmethod
    def _extract_first_match(value: str, pattern: str) -> str:
        if not value:
            return ""
        match = re.search(pattern, value, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return html.unescape(match.group(1).strip())

    @staticmethod
    def _extract_existing_content(existing_html: str) -> str:
        if not existing_html:
            return ""
        match = re.search(
            r'<div class="content">\s*(.*)\s*</div>\s*<div class="footer">',
            existing_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            return match.group(1).strip()
        body_match = re.search(r"<body[^>]*>(.*)</body>", existing_html, flags=re.IGNORECASE | re.DOTALL)
        if body_match:
            return body_match.group(1).strip()
        return existing_html.strip()

    @staticmethod
    def _extract_report_payload_html(existing_html: str) -> str:
        if not existing_html:
            return ""

        report_match = re.search(
            r'<div\s+id="contentDiv\d+"[^>]*>(.*?)</div>\s*<div class="qqmail_attachment_listmargin">',
            existing_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not report_match:
            return existing_html

        report_html = report_match.group(1).strip()
        container_match = re.search(
            r'<div class="container">.*?<div class="footer">.*?</div>\s*</div>',
            report_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if container_match:
            return container_match.group(0).strip()

        return report_html

    @staticmethod
    def _wrap_lead_summary_block(content: str) -> str:
        if not content or 'class="lead-summary"' in content:
            return content

        match = re.search(
            r'^\s*(<h2[^>]*>.*?</h2>\s*(?:<p[^>]*>.*?</p>\s*)+)(.*)$',
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return content

        lead_block = match.group(1).strip()
        rest = match.group(2).lstrip()
        wrapped = f'<div class="lead-summary">{lead_block}</div>'
        if rest:
            wrapped = f"{wrapped}\n\n{rest}"
        return wrapped

    @staticmethod
    def _normalize_persona_text(persona_text: str) -> str:
        if not persona_text:
            return ""
        normalized = re.sub(r"\s*[·•|｜]\s*No fluff, no hype", "", persona_text, flags=re.IGNORECASE)
        normalized = re.sub(r"\s{2,}", " ", normalized)
        return normalized.strip(" ·•|｜")

    @staticmethod
    def _strip_existing_section_marks(content: str) -> str:
        if not content:
            return content
        return re.sub(r'<span class="section-mark(?: [^"]+)?">.*?</span>\s*', "", content, flags=re.IGNORECASE | re.DOTALL)

    @staticmethod
    def _decorate_section_headings(content: str) -> str:
        if not content:
            return content

        heading_map = {
            "今日筛选报告": ('<span class="section-mark summary">🧭</span>', "今日筛选报告"),
            "博客筛选": ('<span class="section-mark blog">📰</span>', "博客筛选"),
            "论文筛选": ('<span class="section-mark paper">📄</span>', "论文筛选"),
            "今日判断摘要": ('<span class="section-mark judgment">📝</span>', "今日判断摘要"),
            "值得知道但暂不主推": ('<span class="section-mark secondary">👀</span>', "值得知道但暂不主推"),
            "Screening Summary": ('<span class="section-mark summary">🧭</span>', "Screening Summary"),
            "Blog Picks": ('<span class="section-mark blog">📰</span>', "Blog Picks"),
            "Paper Picks": ('<span class="section-mark paper">📄</span>', "Paper Picks"),
            "Judgment Summary": ('<span class="section-mark judgment">📝</span>', "Judgment Summary"),
            "Worth Knowing, Not Main Picks": ('<span class="section-mark secondary">👀</span>', "Worth Knowing, Not Main Picks"),
        }

        def replace_heading(match: re.Match[str]) -> str:
            tag = match.group(1)
            attrs = match.group(2)
            inner = match.group(3).strip()
            plain_inner = re.sub(r"<[^>]+>", "", inner).strip()
            if 'section-mark' in inner or plain_inner not in heading_map:
                return match.group(0)
            marker, label = heading_map[plain_inner]
            return f"<{tag}{attrs}>{marker}{label}</{tag}>"

        return re.sub(r"<(h[23])([^>]*)>(.*?)</\1>", replace_heading, content, flags=re.IGNORECASE | re.DOTALL)

    @staticmethod
    def _restyle_feedback_layout(content: str) -> str:
        if not content or "pf-feedback-actions" not in content:
            return content

        def rewrite_brief_item(match: re.Match[str]) -> str:
            body = match.group(1)
            if "pf-feedback-actions" not in body:
                return match.group(0)

            body_match = re.match(
                r'\s*(<strong>.*?</strong>)（\s*(<a [^>]+>.*?</a>)\s*(<span class="pf-feedback-actions">.*?</span>)\s*）[:：]\s*(.*)\s*$',
                body,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not body_match:
                return match.group(0)

            title_html = body_match.group(1).strip()
            link_html = body_match.group(2).strip()
            feedback_html = body_match.group(3).strip()
            comment_html = body_match.group(4).strip()
            return (
                '<li class="pf-brief-item">'
                f'<div class="pf-brief-title">{title_html}</div>'
                f'<div class="pf-brief-link">{link_html}</div>'
                f'<div class="pf-feedback-row">{feedback_html}</div>'
                f'<div class="pf-brief-comment">{comment_html}</div>'
                '</li>'
            )

        content = re.sub(
            r'<li>(.*?)</li>',
            rewrite_brief_item,
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return content

    @staticmethod
    def _inline_title_links(content: str) -> str:
        if not content or "<a " not in content:
            return content

        def rewrite_card_title(match: re.Match[str]) -> str:
            h3_open = match.group(1)
            title_html = match.group(2).strip()
            div_attrs = match.group(4) or ""
            meta_html = match.group(5).strip()
            link_html = match.group(6).strip()
            feedback_html = (match.group(7) or "").strip()
            href_match = re.search(r'href="([^"]+)"', link_html, flags=re.IGNORECASE)
            if not href_match:
                return match.group(0)
            href = href_match.group(1)
            linked_title = f'{h3_open}<a href="{href}" target="_blank">{title_html}</a></h3>'
            meta_line = f'<div{div_attrs}>{meta_html}</div>'
            if feedback_html:
                feedback_block = f'<div class="pf-feedback-row"><span class="pf-feedback-actions">{feedback_html}</span></div>'
                return f'{linked_title}\n  {meta_line}{feedback_block}'
            return f'{linked_title}\n  {meta_line}'

        content = re.sub(
            r'(<h3[^>]*>)(.*?)</h3>\s*(<div([^>]*)>)\s*((?:作者：|来源：)[^<]*?)\s*&nbsp;\|&nbsp;\s*(<a [^>]+>.*?</a>)\s*(?:<span class="pf-feedback-actions">(.*?)</span>)?\s*</div>',
            rewrite_card_title,
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )

        def rewrite_brief_title(match: re.Match[str]) -> str:
            title_html = match.group(1).strip()
            link_html = match.group(2).strip()
            href_match = re.search(r'href="([^"]+)"', link_html, flags=re.IGNORECASE)
            if not href_match:
                return match.group(0)
            href = href_match.group(1)
            return f'<div class="pf-brief-title"><a href="{href}" target="_blank">{title_html}</a></div>'

        content = re.sub(
            r'<div class="pf-brief-title">(.*?)</div>\s*<div class="pf-brief-link">(<a [^>]+>.*?</a>)</div>',
            rewrite_brief_title,
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return content

    def _feedback_note_text(self) -> str:
        if self.language_pack.code == "zh-CN":
            return "注：如果论文没有 Semantic Scholar ID，则不会显示 Like / Dislike feedback。"
        return "Note: papers without a Semantic Scholar ID will not show Like / Dislike feedback."

    def _get_unique_keywords(self, papers: list[Paper]) -> str:
        keywords = set()
        for paper in papers:
            if hasattr(paper, "matched_keywords"):
                keywords.update(paper.matched_keywords)
        return ", ".join(sorted(keywords)[:8]) if keywords else self.language_pack.footer_fallback


ClaudeSummarizer = PaperSummarizer

from __future__ import annotations

import unittest

from paperfeeder.pipeline.prompt_templates import normalize_prompt_language
from paperfeeder.pipeline.summarizer import PaperSummarizer


class PromptLanguageTests(unittest.TestCase):
    def test_language_aliases_normalize(self) -> None:
        self.assertEqual(normalize_prompt_language("zh"), "zh-CN")
        self.assertEqual(normalize_prompt_language("en"), "en-US")
        self.assertEqual(normalize_prompt_language("en-us"), "en-US")
        self.assertEqual(normalize_prompt_language("unknown"), "zh-CN")

    def test_english_prompt_pack_used(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="en")
        prompts = summarizer._build_prompt([], blog_posts=[])
        self.assertIn("## My Research Interests", prompts["user"])
        self.assertIn("Write primarily in English.", prompts["user"])
        self.assertIn("Use a stable 4-section report structure in this order", prompts["user"])
        self.assertIn("Worth Knowing, Not Main Picks", prompts["user"])
        self.assertIn("every remaining paper in today's paper pool", prompts["user"])
        self.assertIn("do not append counts in parentheses", prompts["user"])
        self.assertIn("single compact sentence", prompts["user"])
        self.assertIn("Judgment Summary", prompts["user"])
        self.assertIn("3 to 4 short bullets", prompts["user"])
        self.assertIn("Do not include any skipped/rejected/not-selected section", prompts["user"])
        self.assertIn("one compact overview paragraph plus 3 short bullets", prompts["user"])
        self.assertIn("Do not output raw markdown separators like ---.", prompts["user"])
        self.assertIn("must sit on its own line above the title", prompts["user"])
        html = summarizer._wrap_html("<p>Test</p>", [], [])
        self.assertIn("Paper Digest", html)
        self.assertIn("0 papers reviewed", html)
        self.assertIn("Curated by PaperFeeder", html)
        self.assertNotIn("No fluff, no hype", html)
        self.assertIn("Semantic Scholar ID", html)

    def test_chinese_prompt_pack_used(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        prompts = summarizer._build_prompt([], blog_posts=[])
        self.assertIn("## 我的研究兴趣", prompts["user"])
        self.assertIn("输出语言以简体中文为主", prompts["user"])
        self.assertIn("最终报告优先使用固定的 4 个一级 section", prompts["user"])
        self.assertIn("值得知道但暂不主推", prompts["user"])
        self.assertIn("剩下没有展开深读的论文", prompts["user"])
        self.assertIn("不要在标题后面加括号", prompts["user"])
        self.assertIn("每篇严格控制为一句短评", prompts["user"])
        self.assertIn("今日判断摘要", prompts["user"])
        self.assertIn("3 到 4 个短 bullet", prompts["user"])
        self.assertIn("不要在最终报告里写任何\"跳过/未入选/skip\"区块", prompts["user"])
        self.assertIn("1 段简洁概述 + 3 个短要点", prompts["user"])
        self.assertIn("不要输出裸露的 markdown 分隔线", prompts["user"])
        self.assertIn("标签、来源、category badge、推荐标记等元信息必须单独占一行", prompts["user"])
        html = summarizer._wrap_html("<p>测试</p>", [], [])
        self.assertIn("已审阅 0 篇论文", html)
        self.assertIn("Curated by PaperFeeder", html)
        self.assertNotIn("No fluff, no hype", html)
        self.assertIn("Semantic Scholar ID", html)

    def test_strip_skip_sections_removes_skipped_block(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        content = (
            "<section><h2>⏭ 跳过（8 篇）— 理由</h2><ul><li>Paper A</li></ul></section>"
            "<section><h2>推荐阅读</h2><p>保留内容</p></section>"
        )
        cleaned = summarizer._strip_skip_sections(content)
        self.assertNotIn("跳过（8 篇）", cleaned)
        self.assertNotIn("Paper A", cleaned)
        self.assertIn("推荐阅读", cleaned)

    def test_strip_raw_separators_removes_markdown_rules_but_keeps_summary_block(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        content = "<section><h2>今日评判摘要</h2><p>保留</p></section><p>---</p>\n---\n<section><h2>推荐阅读</h2></section>"
        cleaned = summarizer._strip_raw_separators(content)
        self.assertNotIn("<p>---</p>", cleaned)
        self.assertNotIn("\n---\n", cleaned)
        self.assertIn("今日评判摘要", cleaned)
        self.assertIn("推荐阅读", cleaned)

    def test_split_badge_and_title_lines_inserts_break_after_badge(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        content = '<p><span class="badge">RL · 文本反馈</span><a href="https://example.com">Example Title</a></p>'
        cleaned = summarizer._split_badge_and_title_lines(content)
        self.assertIn("</span><br><a ", cleaned)

    def test_strip_secondary_heading_counts_removes_parenthesized_counts(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        content = "<section><h3>值得知道但暂不主推（4 篇）</h3><p>短评</p></section>"
        cleaned = summarizer._strip_secondary_heading_counts(content)
        self.assertIn("值得知道但暂不主推</h3>", cleaned)
        self.assertNotIn("（4 篇）", cleaned)

    def test_rewrap_existing_report_html_preserves_content_and_meta(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        existing_html = """
        <html><body>
        <div class="container">
            <div class="header">
                <h1>Paper Digest</h1>
                <div class="meta">2026年03月21日 周六 · 已审阅 8 篇论文 + 10 篇博客</div>
                <div class="persona">Curated by PaperFeeder · No fluff, no hype</div>
            </div>
            <div class="content"><section><h2>今日筛选报告</h2><p>保留内容</p></section></div>
            <div class="footer">PaperFeeder · alignment, llm</div>
        </div>
        </body></html>
        """
        wrapped = summarizer.rewrap_existing_report_html(existing_html)
        self.assertIn("保留内容", wrapped)
        self.assertIn("已审阅 8 篇论文 + 10 篇博客", wrapped)
        self.assertIn("PaperFeeder · alignment, llm", wrapped)
        self.assertNotIn("No fluff, no hype", wrapped)

    def test_rewrap_existing_report_html_extracts_saved_qmail_body(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        existing_html = """
        <html><body>
        <div id="contentDiv0" class="qm_bigsize qm_converstaion_body body">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <div class="container">
                <div class="header">
                    <h1>Paper Digest</h1>
                    <div class="meta">2026年03月22日 周日 · 已审阅 10 篇论文 + 2 篇博客</div>
                    <div class="persona">Curated by PaperFeeder · No fluff, no hype</div>
                </div>
                <div class="content"><h2>今日筛选报告</h2><p>从 today.html 提取</p></div>
                <div class="footer">PaperFeeder · alignment, reasoning</div>
            </div>
        </div>
        <div class="qqmail_attachment_listmargin"></div>
        </body></html>
        """
        wrapped = summarizer.rewrap_existing_report_html(existing_html)
        self.assertIn("从 today.html 提取", wrapped)
        self.assertIn("已审阅 10 篇论文 + 2 篇博客", wrapped)
        self.assertIn("PaperFeeder · alignment, reasoning", wrapped)
        self.assertNotIn("No fluff, no hype", wrapped)

    def test_wrap_lead_summary_block_only_wraps_top_summary(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        content = """
        <h2>今日筛选报告</h2>
        <p>顶部摘要</p>
        <hr>
        <h2>博客筛选</h2>
        <section><p>后续内容</p></section>
        """
        wrapped = summarizer._wrap_lead_summary_block(content)
        self.assertIn('<div class="lead-summary"><h2>今日筛选报告</h2>', wrapped)
        self.assertIn('<h2>博客筛选</h2>', wrapped)
        self.assertEqual(wrapped.count('class="lead-summary"'), 1)

    def test_decorate_section_headings_adds_symbols(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        content = "<h2>今日筛选报告</h2><h2>博客筛选</h2><h3>值得知道但暂不主推</h3>"
        decorated = summarizer._decorate_section_headings(content)
        self.assertIn('<span class="section-mark summary">🧭</span>今日筛选报告', decorated)
        self.assertIn('<span class="section-mark blog">📰</span>博客筛选', decorated)
        self.assertIn('<span class="section-mark secondary">👀</span>值得知道但暂不主推', decorated)

    def test_strip_existing_section_marks_removes_old_symbols_before_redecorate(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        content = '<h2><span class="section-mark">✦</span>今日筛选报告</h2>'
        stripped = summarizer._strip_existing_section_marks(content)
        self.assertEqual(stripped, '<h2>今日筛选报告</h2>')

    def test_restyle_feedback_layout_splits_brief_item_lines(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        content = (
            '<li><strong>Paper A</strong>（<a href="https://example.com">链接</a>'
            '<span class="pf-feedback-actions"><a class="pf-feedback-btn undecided" href="https://feedback">🤔 Undecided</a></span>）：'
            '一行短评。</li>'
        )
        restyled = summarizer._restyle_feedback_layout(content)
        self.assertIn('class="pf-brief-item"', restyled)
        self.assertIn('class="pf-brief-title"><strong>Paper A</strong></div>', restyled)
        self.assertIn('class="pf-brief-link"><a href="https://example.com">链接</a></div>', restyled)
        self.assertIn('class="pf-feedback-row"><span class="pf-feedback-actions">', restyled)
        self.assertIn('class="pf-brief-comment">一行短评。</div>', restyled)

    def test_restyle_feedback_layout_does_not_touch_regular_bullets(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        content = '<li><strong>普通 bullet</strong>：没有 feedback，不应被改写。</li>'
        restyled = summarizer._restyle_feedback_layout(content)
        self.assertEqual(restyled, content)

    def test_inline_title_links_moves_card_link_into_heading(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        content = (
            '<h3>Paper Title</h3>'
            '<div>作者：Alice &nbsp;|&nbsp; <a href="https://example.com/paper">arXiv 链接</a></div>'
        )
        updated = summarizer._inline_title_links(content)
        self.assertIn('<h3><a href="https://example.com/paper" target="_blank">Paper Title</a></h3>', updated)
        self.assertIn('<div>作者：Alice</div>', updated)
        self.assertNotIn('arXiv 链接', updated)

    def test_inline_title_links_keeps_feedback_block_with_card(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        content = (
            '<h3>Paper Title</h3>'
            '<div style="font-size:0.85em;">作者：Alice &nbsp;|&nbsp; <a href="https://example.com/paper">arXiv 链接</a>'
            '<span class="pf-feedback-actions"><a class="pf-feedback-btn positive" href="https://feedback">👍 Positive</a></span></div>'
            '<section><ul><li><strong>Other Paper</strong>（<a href="https://example.com/other">链接</a>）：短评</li></ul></section>'
        )
        updated = summarizer._inline_title_links(content)
        self.assertIn('<h3><a href="https://example.com/paper" target="_blank">Paper Title</a></h3>', updated)
        self.assertIn('<div style="font-size:0.85em;">作者：Alice</div><div class="pf-feedback-row"><span class="pf-feedback-actions"><a class="pf-feedback-btn positive" href="https://feedback">👍 Positive</a></span></div>', updated)
        self.assertIn('<section><ul><li><strong>Other Paper</strong>（<a href="https://example.com/other">链接</a>）：短评</li></ul></section>', updated)

    def test_inline_title_links_moves_brief_link_into_title(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        content = (
            '<li class="pf-brief-item">'
            '<div class="pf-brief-title"><strong>Paper A</strong></div>'
            '<div class="pf-brief-link"><a href="https://example.com/paper">链接</a></div>'
            '<div class="pf-feedback-row"><span class="pf-feedback-actions"></span></div>'
            '<div class="pf-brief-comment">短评</div>'
            '</li>'
        )
        updated = summarizer._inline_title_links(content)
        self.assertIn('<div class="pf-brief-title"><a href="https://example.com/paper" target="_blank"><strong>Paper A</strong></a></div>', updated)
        self.assertNotIn('class="pf-brief-link"', updated)

if __name__ == "__main__":
    unittest.main()
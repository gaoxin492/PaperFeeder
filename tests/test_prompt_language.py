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
        self.assertIn("Do not include any skipped/rejected/not-selected section", prompts["user"])
        self.assertIn("one compact overview paragraph plus 3 short bullets", prompts["user"])
        self.assertIn("Do not output raw markdown separators like ---.", prompts["user"])
        self.assertIn("must sit on its own line above the title", prompts["user"])
        html = summarizer._wrap_html("<p>Test</p>", [], [])
        self.assertIn("Paper Digest", html)
        self.assertIn("0 papers reviewed", html)
        self.assertIn("No fluff, no hype", html)

    def test_chinese_prompt_pack_used(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        prompts = summarizer._build_prompt([], blog_posts=[])
        self.assertIn("## 我的研究兴趣", prompts["user"])
        self.assertIn("输出语言以简体中文为主", prompts["user"])
        self.assertIn("不要在最终报告里写任何\"跳过/未入选/skip\"区块", prompts["user"])
        self.assertIn("1 段简洁概述 + 3 个短要点", prompts["user"])
        self.assertIn("不要输出裸露的 markdown 分隔线", prompts["user"])
        self.assertIn("标签、来源、category badge、推荐标记等元信息必须单独占一行", prompts["user"])
        html = summarizer._wrap_html("<p>测试</p>", [], [])
        self.assertIn("已审阅 0 篇论文", html)
        self.assertIn("No fluff, no hype", html)

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


if __name__ == "__main__":
    unittest.main()
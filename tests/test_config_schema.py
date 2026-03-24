"""Tests for config schema helpers and feedback-related settings."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from paperfeeder.config.schema import Config, _parse_loose_bool
from paperfeeder.pipeline.runner import _feedback_email_attachment_paths


class ParseLooseBoolTests(unittest.TestCase):
    def test_yaml_string_false_disables(self) -> None:
        self.assertFalse(_parse_loose_bool("false", default=True))
        self.assertFalse(_parse_loose_bool("FALSE", default=True))
        self.assertFalse(_parse_loose_bool("0", default=True))
        self.assertFalse(_parse_loose_bool("no", default=True))
        self.assertFalse(_parse_loose_bool("off", default=True))

    def test_real_bool(self) -> None:
        self.assertTrue(_parse_loose_bool(True, default=False))
        self.assertFalse(_parse_loose_bool(False, default=True))

    def test_default_on_none_or_empty_string(self) -> None:
        self.assertTrue(_parse_loose_bool(None, default=True))
        self.assertFalse(_parse_loose_bool(None, default=False))
        self.assertTrue(_parse_loose_bool("", default=True))


class FeedbackWebViewerFromYamlTests(unittest.TestCase):
    def test_quoted_false_string_in_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.yaml"
            cfg.write_text(
                "feedback_web_viewer_link_in_email: 'false'\n"
                "email_to: x@y.z\n",
                encoding="utf-8",
            )
            c = Config.from_yaml(str(cfg))
            self.assertFalse(c.feedback_web_viewer_link_in_email)

    def test_semantic_state_backend_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.yaml"
            cfg.write_text(
                "semantic_state_backend: file\n"
                "email_to: x@y.z\n",
                encoding="utf-8",
            )
            old_backend = os.environ.get("SEMANTIC_STATE_BACKEND")
            os.environ["SEMANTIC_STATE_BACKEND"] = "d1"
            try:
                loaded = Config.from_yaml(str(cfg))
            finally:
                if old_backend is None:
                    os.environ.pop("SEMANTIC_STATE_BACKEND", None)
                else:
                    os.environ["SEMANTIC_STATE_BACKEND"] = old_backend

            self.assertEqual(loaded.semantic_state_backend, "d1")


class UserPersonalizationFileTests(unittest.TestCase):
    def test_user_list_files_override_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_dir = root / "user"
            user_dir.mkdir()

            cfg = root / "config.yaml"
            cfg.write_text(
                "keywords:\n"
                "  - baseline keyword\n"
                "exclude_keywords:\n"
                "  - baseline exclude\n"
                "arxiv_categories:\n"
                "  - cs.CL\n",
                encoding="utf-8",
            )
            (user_dir / "keywords.txt").write_text(
                "reasoning\n"
                "latent reasoning # inline comment\n"
                "\n"
                "# full line comment\n",
                encoding="utf-8",
            )
            (user_dir / "exclude_keywords.txt").write_text(
                "medical\n"
                "robotics\n",
                encoding="utf-8",
            )
            (user_dir / "arxiv_categories.txt").write_text(
                "cs.LG\n"
                "cs.AI\n",
                encoding="utf-8",
            )

            cwd = Path.cwd()
            try:
                os.chdir(root)
                loaded = Config.from_yaml(str(cfg))
            finally:
                os.chdir(cwd)

            self.assertEqual(loaded.keywords, ["reasoning", "latent reasoning"])
            self.assertEqual(loaded.exclude_keywords, ["medical", "robotics"])
            self.assertEqual(loaded.arxiv_categories, ["cs.LG", "cs.AI"])

    def test_user_blog_settings_file_overrides_blog_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_dir = root / "user"
            user_dir.mkdir()
            cfg = root / "config.yaml"
            cfg.write_text(
                "blogs_enabled: true\n"
                "user_blog_settings_path: user/blogs.yaml\n",
                encoding="utf-8",
            )

            (user_dir / "blogs.yaml").write_text(
                "enabled_blogs:\n"
                "  - openai\n"
                "  - huggingface\n"
                "custom_blogs:\n"
                "  my_lab:\n"
                "    name: My Lab Blog\n"
                "    feed_url: https://example.com/feed.xml\n"
                "    website: https://example.com/blog/\n"
                "    priority: true\n",
                encoding="utf-8",
            )

            cwd = Path.cwd()
            try:
                os.chdir(root)
                loaded = Config.from_yaml(str(cfg))
            finally:
                os.chdir(cwd)

            self.assertEqual(loaded.enabled_blogs, ["openai", "huggingface"])
            self.assertEqual(loaded.custom_blogs["my_lab"]["website"], "https://example.com/blog/")

    def test_max_blog_posts_from_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.yaml"
            cfg.write_text(
                "max_blog_posts: 4\n"
                "email_to: x@y.z\n",
                encoding="utf-8",
            )
            loaded = Config.from_yaml(str(cfg))
            self.assertEqual(loaded.max_blog_posts, 4)


class BlogFilteringTests(unittest.TestCase):
    def test_blog_keyword_filter_and_cap(self) -> None:
        from paperfeeder.models import Paper, PaperSource
        from paperfeeder.pipeline.runner import filter_blog_posts

        config = Config(
            keywords=["alignment", "reasoning"],
            exclude_keywords=["product"],
            max_blog_posts=2,
        )
        posts = [
            Paper(
                title="Alignment monitoring in coding agents",
                abstract="alignment research notes",
                url="https://example.com/1",
                source=PaperSource.MANUAL,
            ),
            Paper(
                title="Reasoning evals in frontier models",
                abstract="reasoning benchmark",
                url="https://example.com/2",
                source=PaperSource.MANUAL,
            ),
            Paper(
                title="Product launch",
                abstract="new product announcement",
                url="https://example.com/3",
                source=PaperSource.MANUAL,
            ),
        ]

        filtered = filter_blog_posts(posts, config)
        self.assertEqual(len(filtered), 2)
        self.assertEqual([paper.url for paper in filtered], ["https://example.com/1", "https://example.com/2"])


class FeedbackEmailAttachmentPathsTests(unittest.TestCase):
    def test_modes(self) -> None:
        m, q = "/a/manifest.json", "/a/template.json"
        self.assertEqual(_feedback_email_attachment_paths("all", m, q), [m, q])
        self.assertEqual(_feedback_email_attachment_paths("manifest", m, q), [m])
        self.assertEqual(_feedback_email_attachment_paths("none", m, q), [])


if __name__ == "__main__":
    unittest.main()


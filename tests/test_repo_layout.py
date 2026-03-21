from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path


class RepoLayoutTests(unittest.TestCase):
    def test_package_runner_exports_helpers(self) -> None:
        runner = importlib.import_module("paperfeeder.pipeline.runner")
        self.assertTrue(callable(runner.main))
        self.assertTrue(callable(runner.run_pipeline))
        self.assertTrue(callable(runner._extract_report_urls))

    def test_feedback_cli_imports(self) -> None:
        feedback = importlib.import_module("paperfeeder.cli.apply_feedback")
        self.assertTrue(callable(feedback.main))

    def test_feedback_cli_loads_dotenv(self) -> None:
        feedback = importlib.import_module("paperfeeder.cli.apply_feedback")

        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("CLOUDFLARE_ACCOUNT_ID=from-dotenv\n", encoding="utf-8")

            old_cwd = Path.cwd()
            old_value = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
            try:
                os.chdir(tmp)
                os.environ.pop("CLOUDFLARE_ACCOUNT_ID", None)
                feedback.load_cli_env()
                self.assertEqual(os.environ.get("CLOUDFLARE_ACCOUNT_ID"), "from-dotenv")
            finally:
                os.chdir(old_cwd)
                if old_value is None:
                    os.environ.pop("CLOUDFLARE_ACCOUNT_ID", None)
                else:
                    os.environ["CLOUDFLARE_ACCOUNT_ID"] = old_value

    def test_profile_templates_exist(self) -> None:
        root = Path(__file__).resolve().parent.parent
        profile_names = [
            "frontier-ai-lab",
            "interpretability-alignment",
            "coding-agents-reasoning",
            "multimodal-generative",
        ]
        required_files = [
            "research_interests.txt",
            "keywords.txt",
            "exclude_keywords.txt",
            "arxiv_categories.txt",
        ]

        for profile_name in profile_names:
            profile_dir = root / "user" / "examples" / "profiles" / profile_name
            self.assertTrue(profile_dir.is_dir(), msg=f"missing profile dir: {profile_name}")
            for required_file in required_files:
                self.assertTrue(
                    (profile_dir / required_file).is_file(),
                    msg=f"missing {required_file} in profile {profile_name}",
                )


if __name__ == "__main__":
    unittest.main()

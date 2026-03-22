from __future__ import annotations

import argparse
from pathlib import Path

from paperfeeder.config import Config, DEFAULT_CONFIG_PATH, DEFAULT_REPORT_PREVIEW_PATH
from paperfeeder.pipeline.summarizer import PaperSummarizer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rewrap an existing digest HTML with the current email template")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to config file")
    parser.add_argument(
        "--input",
        default=DEFAULT_REPORT_PREVIEW_PATH,
        help="Existing full HTML report to reuse as content (default: report_preview.html)",
    )
    parser.add_argument(
        "--output",
        default="template_preview.html",
        help="Where to write the rewrapped preview HTML",
    )
    return parser


def _read_html_input(path: Path) -> str:
    encodings = ("utf-8", "gb18030", "gbk", "latin-1")
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Unable to read input HTML: {path}")


def main() -> None:
    args = build_parser().parse_args()
    input_path = Path(args.input)
    if not input_path.is_file():
        raise FileNotFoundError(f"Input HTML not found: {input_path}")

    config = Config.from_yaml(args.config)
    summarizer = PaperSummarizer(
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
        model=config.llm_model,
        research_interests=config.research_interests,
        prompt_addon=getattr(config, "prompt_addon", ""),
        prompt_language=getattr(config, "prompt_language", "zh-CN"),
        debug_save_pdfs=getattr(config, "debug_save_pdfs", False),
        debug_pdf_dir=getattr(config, "debug_pdf_dir", "debug_pdfs"),
        pdf_max_pages=getattr(config, "pdf_max_pages", 10),
    )

    existing_html = _read_html_input(input_path)
    preview_html = summarizer.rewrap_existing_report_html(existing_html)
    output_path = Path(args.output)
    output_path.write_text(preview_html, encoding="utf-8")
    print(f"Template preview saved to {output_path}")


if __name__ == "__main__":
    main()
from __future__ import annotations

import argparse
import asyncio
import base64
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlsplit, urlunsplit

from paperfeeder.config import Config, DEFAULT_ARTIFACTS_DIR, DEFAULT_CONFIG_PATH, DEFAULT_REPORT_PREVIEW_PATH
from paperfeeder.models import Paper, PaperSource
from paperfeeder.semantic import (
    SemanticMemoryStore,
    append_feedback_fallback_strip,
    export_run_feedback_manifest,
    inject_feedback_actions_into_report,
    make_email_safe_report_html,
    memory_keys_for_paper,
    publish_feedback_run_to_d1,
)


async def fetch_papers(config: Config, days_back: int = 1) -> List[Paper]:
    from paperfeeder.sources import ArxivSource, HuggingFaceSource, ManualSource, SemanticScholarSource

    papers = []
    memory_store = None

    setattr(config, "_semantic_memory_store", None)
    if getattr(config, "semantic_memory_enabled", True):
        memory_store = SemanticMemoryStore(
            path=getattr(config, "semantic_memory_path", "state/semantic/memory.json"),
            max_ids=getattr(config, "semantic_memory_max_ids", 5000),
        )
        memory_store.load()
        pruned = memory_store.prune_expired(getattr(config, "semantic_seen_ttl_days", 30))
        if pruned:
            print(f"      Semantic memory pruned expired seen IDs: {pruned}")
        setattr(config, "_semantic_memory_store", memory_store)

    def suppress_by_memory(candidates: List[Paper], source_label: str) -> List[Paper]:
        if not memory_store:
            return candidates
        try:
            ttl_days = getattr(config, "semantic_seen_ttl_days", 30)
            filtered: List[Paper] = []
            for paper in candidates:
                keys = memory_keys_for_paper(paper)
                if keys and memory_store.recently_seen_any(keys, ttl_days=ttl_days):
                    continue
                filtered.append(paper)
            suppressed = len(candidates) - len(filtered)
            if suppressed:
                print(
                    f"      {source_label} suppression: "
                    f"total={len(candidates)}, suppressed={suppressed}, forwarded={len(filtered)}"
                )
            return filtered
        except Exception as exc:
            print(f"      {source_label} suppression failed, proceeding without suppression: {exc}")
            return candidates

    print("Fetching from arXiv...")
    arxiv_source = ArxivSource(config.arxiv_categories)
    arxiv_papers = await arxiv_source.fetch(days_back=days_back, max_results=300)
    arxiv_papers = suppress_by_memory(arxiv_papers, "arXiv")
    papers.extend(arxiv_papers)
    print(f"   Found {len(arxiv_papers)} papers")

    print("Fetching from HuggingFace Daily Papers...")
    hf_source = HuggingFaceSource()
    hf_papers = await hf_source.fetch()
    hf_papers = suppress_by_memory(hf_papers, "HuggingFace")
    papers.extend(hf_papers)
    print(f"   Found {len(hf_papers)} papers")

    if config.manual_source_enabled:
        print("Fetching manual additions...")
        manual_source = ManualSource(config.manual_source_path)
        manual_papers = await manual_source.fetch()
        papers.extend(manual_papers)
        print(f"   Found {len(manual_papers)} papers")

    if getattr(config, "semantic_scholar_enabled", False):
        print("Fetching from Semantic Scholar recommendations...")
        s2_source = SemanticScholarSource(
            api_key=getattr(config, "semantic_scholar_api_key", ""),
            seeds_path=getattr(config, "semantic_scholar_seeds_path", "state/semantic/seeds.json"),
            max_results=getattr(config, "semantic_scholar_max_results", 50),
            memory_store=memory_store,
            seen_ttl_days=getattr(config, "semantic_seen_ttl_days", 30),
        )
        s2_papers = await s2_source.fetch()
        papers.extend(s2_papers)
        print(f"   Found {len(s2_papers)} papers")
        stats = getattr(s2_source, "last_stats", None)
        if stats:
            print(
                "   Semantic Scholar stats: "
                f"total={stats.get('total', 0)}, suppressed={stats.get('suppressed', 0)}, "
                f"forwarded={stats.get('forwarded', 0)}"
            )

    seen = set()
    unique_papers = []
    for paper in papers:
        key = paper.arxiv_id or paper.url
        if key not in seen:
            seen.add(key)
            unique_papers.append(paper)

    print(f"Total unique papers: {len(unique_papers)}")
    return unique_papers


def _normalize_url_for_match(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower() if parts.scheme else "https"
        netloc = parts.netloc.lower()
        path = parts.path.rstrip("/")
        return urlunsplit((scheme, netloc, path, "", ""))
    except Exception:
        return url.strip().lower().rstrip("/")


def _extract_report_urls(report_html: str) -> set[str]:
    if not report_html:
        return set()
    urls = set()
    for raw in re.findall(r'href=["\']([^"\']+)["\']', report_html, flags=re.IGNORECASE):
        norm = _normalize_url_for_match(raw)
        if norm:
            urls.add(norm)
    return urls


def update_semantic_memory_from_report(final_papers: List[Paper], report_html: str, config: Config) -> None:
    if not getattr(config, "semantic_memory_enabled", True):
        return

    memory_store = getattr(config, "_semantic_memory_store", None)
    if memory_store is None:
        return

    report_urls = _extract_report_urls(report_html)
    final_memory_candidates = [
        paper
        for paper in final_papers
        if getattr(paper, "source", None)
        in {PaperSource.SEMANTIC_SCHOLAR, PaperSource.ARXIV, PaperSource.HUGGINGFACE}
    ]
    if not final_memory_candidates:
        print("   Semantic memory: no final papers eligible for memory")
        return

    visible_papers = [
        paper for paper in final_memory_candidates if _normalize_url_for_match(getattr(paper, "url", "")) in report_urls
    ]
    if not visible_papers:
        print(
            "   Semantic memory: no report-visible final papers to update "
            f"(final_selected={len(final_memory_candidates)})"
        )
        return

    visible_keys = sorted({key for paper in visible_papers for key in memory_keys_for_paper(paper)})
    if not visible_keys:
        print(
            "   Semantic memory: report-visible papers had no usable memory keys "
            f"(report_visible={len(visible_papers)})"
        )
        return

    try:
        memory_store.mark_seen(visible_keys)
        removed = memory_store.prune_expired(getattr(config, "semantic_seen_ttl_days", 30))
        memory_store.save()
        print(
            "   Semantic memory updated: "
            f"final_selected={len(final_memory_candidates)}, report_visible={len(visible_papers)}, "
            f"seen_keys_added={len(visible_keys)}, expired_removed={removed}"
        )
    except Exception as exc:
        print(f"   Semantic memory update failed (non-blocking): {exc}")


async def fetch_blogs(config: Config, days_back: int = 7) -> tuple[List[Paper], List[Paper]]:
    try:
        from paperfeeder.sources import BlogSource
    except ImportError:
        return [], []
    if not getattr(config, "blogs_enabled", True):
        return [], []

    print("Fetching from blogs...")
    source = BlogSource(
        enabled_blogs=getattr(config, "enabled_blogs", None),
        custom_blogs=getattr(config, "custom_blogs", None),
        include_non_priority=True,
    )
    all_posts = await source.fetch(days_back=getattr(config, "blog_days_back", days_back), max_posts_per_blog=5)
    print(f"   Blogs fetched before filtering: {len(all_posts)}")
    return [], all_posts


def filter_blog_posts(posts: List[Paper], config: Config) -> List[Paper]:
    from paperfeeder.pipeline.filters import KeywordFilter

    if not posts:
        return []

    print(f"\nFiltering {len(posts)} blogs...")
    keyword_filter = KeywordFilter(keywords=config.keywords, exclude_keywords=config.exclude_keywords)
    filtered = keyword_filter.filter(posts)
    print(f"   Blog prefilter (exclude + keyword): {len(filtered)} posts matched")

    max_blog_posts = max(0, int(getattr(config, "max_blog_posts", 5) or 0))
    if max_blog_posts and len(filtered) > max_blog_posts:
        filtered = filtered[:max_blog_posts]
        print(f"   Blog cap applied: keeping top {len(filtered)} posts")

    return filtered


async def filter_papers_coarse(papers: List[Paper], config: Config) -> List[Paper]:
    from paperfeeder.pipeline.filters import KeywordFilter, LLMFilter

    print(f"\nFiltering {len(papers)} papers...")
    keyword_filter = KeywordFilter(keywords=config.keywords, exclude_keywords=config.exclude_keywords)
    filtered = keyword_filter.filter(papers)
    print(f"   Keyword filter: {len(filtered)} papers matched")

    if config.llm_filter_enabled and len(filtered) > config.llm_filter_threshold:
        llm_filter = LLMFilter(
            api_key=config.llm_filter_api_key,
            research_interests=config.research_interests,
            prompt_addon=getattr(config, "prompt_addon", ""),
            base_url=config.llm_filter_base_url,
            model=config.llm_filter_model,
        )
        filtered = await llm_filter.filter(filtered, max_papers=20, include_community_signals=False)
        print(f"   LLM coarse filter: {len(filtered)} papers selected for enrichment")
    elif config.llm_filter_enabled:
        print(f"   Skipping LLM coarse filter (only {len(filtered)} papers)")

    return filtered


async def enrich_papers(papers: List[Paper], config: Config) -> List[Paper]:
    from paperfeeder.pipeline.researcher import MockPaperResearcher, PaperResearcher

    tavily_api_key = config.tavily_api_key
    if not tavily_api_key:
        print("   TAVILY_API_KEY not found, using mock researcher")
        researcher = MockPaperResearcher()
    else:
        print("   Using Tavily API for research")
        researcher = PaperResearcher(api_key=tavily_api_key, max_concurrent=5, search_depth="basic")
    return await researcher.research(papers)


async def filter_papers_fine(papers: List[Paper], config: Config) -> List[Paper]:
    from paperfeeder.pipeline.filters import LLMFilter

    if not config.llm_filter_enabled:
        print("   LLM filter disabled, returning all papers")
        return papers[: config.max_papers]

    llm_filter = LLMFilter(
        api_key=config.llm_filter_api_key,
        research_interests=config.research_interests,
        prompt_addon=getattr(config, "prompt_addon", ""),
        base_url=config.llm_filter_base_url,
        model=config.llm_filter_model,
    )
    final_papers = await llm_filter.filter(papers, max_papers=config.max_papers, include_community_signals=True)
    print(f"   LLM fine filter: selected {len(final_papers)} papers for final report")
    return final_papers


async def summarize_papers(
    papers: list[Paper],
    config: Config,
    priority_blogs: list[Paper] | None = None,
) -> str:
    from paperfeeder.pipeline.summarizer import PaperSummarizer

    all_content = []
    if priority_blogs:
        all_content.extend(priority_blogs)
    all_content.extend(papers)

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
    return await summarizer.generate_report(all_content, use_pdf_multimodal=config.extract_fulltext)


async def send_email(report: str, config: Config, attachments: Optional[List[dict]] = None) -> bool:
    from paperfeeder.email import ResendEmailer

    emailer = ResendEmailer(api_key=config.resend_api_key, from_email=config.email_from)
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"Daily Paper Digest - {today}"
    success = await emailer.send(
        to=config.email_to,
        subject=subject,
        html_content=report,
        attachments=attachments or [],
    )
    if success:
        print("   Email sent successfully")
    else:
        print("   Failed to send email")
    return success


def _build_email_attachments(paths: List[str]) -> List[dict]:
    attachments: List[dict] = []
    for path_str in paths:
        path = Path(path_str)
        if not path.exists() or not path.is_file():
            continue
        content = base64.b64encode(path.read_bytes()).decode("ascii")
        attachments.append(
            {
                "filename": path.name,
                "content": content,
                "content_type": "application/json",
            }
        )
    return attachments


def _feedback_email_attachment_paths(
    mode: str, manifest_path: str, questionnaire_path: str
) -> List[str]:
    """
    Which feedback JSON files to attach to the digest email.

    Modes: all (manifest + questionnaire template), manifest, none.
    """
    m = (mode or "all").strip().lower()
    if m in ("none", "off", "false", "0", "no"):
        return []
    if m in ("manifest", "manifest_only"):
        return [manifest_path]
    # all, both, full, or unknown → keep previous default (both files)
    return [manifest_path, questionnaire_path]


async def run_pipeline(
    config_path: str = DEFAULT_CONFIG_PATH,
    days_back: int = 1,
    dry_run: bool = False,
    no_papers: bool = False,
    no_blogs: bool = False,
    debug_sample: bool = False,
    debug_sample_path: Optional[str] = None,
    debug_minimal_report: bool = False,
    debug_llm_report: bool = False,
    debug_write_memory: bool = False,
):
    print("=" * 80)
    print(f"PaperFeeder - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    if debug_sample:
        print("\n*** DEBUG SAMPLE MODE ***")
        print("    Skips: paper fetch, blogs, coarse/fine LLM filters, Tavily enrichment.")
        if debug_llm_report:
            print("    Main digest LLM: ON (--debug-llm-report).")
        else:
            print("    Main digest LLM: OFF (fixed stub HTML; use --debug-llm-report to enable).")
        if not debug_write_memory:
            print("    Skips: semantic memory file update (use --debug-write-memory to enable).")
        print()

    if no_papers:
        os.environ["PAPERS_ENABLED"] = "false"
    if no_blogs:
        os.environ["BLOGS_ENABLED"] = "false"

    config = Config.from_yaml(config_path)

    if debug_sample:
        from paperfeeder.pipeline.debug_sample import load_debug_sample_papers

        papers = load_debug_sample_papers(debug_sample_path)
        priority_blogs, normal_blogs = [], []
        all_blogs = []
        coarse_filtered = papers
        enriched_papers = papers
        final_papers = papers
    else:
        papers = []
        if getattr(config, "papers_enabled", True):
            papers = await fetch_papers(config, days_back=days_back)
        else:
            print("   Paper fetching disabled")

        priority_blogs, normal_blogs = await fetch_blogs(config, days_back=7)
        all_blogs = filter_blog_posts(priority_blogs + normal_blogs, config)

        if not papers and not all_blogs:
            print("No papers or blogs found. Exiting.")
            return

        coarse_filtered = []
        if papers:
            coarse_filtered = await filter_papers_coarse(papers, config)

        if not coarse_filtered and not all_blogs:
            print("No papers passed coarse filter and no blogs. Exiting.")
            return

        enriched_papers = []
        if coarse_filtered:
            enriched_papers = await enrich_papers(coarse_filtered, config)

        final_papers = []
        if enriched_papers:
            final_papers = await filter_papers_fine(enriched_papers, config)

        if not final_papers and not all_blogs:
            print("No papers passed fine filter and no blogs. Exiting.")
            return

    from paperfeeder.pipeline.debug_sample import build_minimal_digest_html

    # Debug sample: default = no main digest LLM (stub only). Full run: LLM unless --debug-minimal-report.
    if debug_sample:
        use_digest_llm = bool(debug_llm_report)
    else:
        use_digest_llm = not bool(debug_minimal_report)

    if use_digest_llm:
        report = await summarize_papers(final_papers, config, priority_blogs=all_blogs)
    else:
        report = build_minimal_digest_html(final_papers)
    email_report = report
    feedback_artifacts: Optional[tuple] = None

    try:
        feedback_artifacts = export_run_feedback_manifest(
            final_papers,
            report,
            output_dir=DEFAULT_ARTIFACTS_DIR,
            feedback_endpoint_base_url=getattr(config, "feedback_endpoint_base_url", ""),
            feedback_link_signing_secret=getattr(config, "feedback_link_signing_secret", ""),
            reviewer=getattr(config, "feedback_reviewer", "") or getattr(config, "email_to", ""),
            token_ttl_days=getattr(config, "feedback_token_ttl_days", 7),
            semantic_scholar_api_key=getattr(config, "semantic_scholar_api_key", ""),
            resolver_enabled=getattr(config, "feedback_resolution_enabled", True),
            resolver_timeout_sec=getattr(config, "feedback_resolution_timeout_sec", 8),
            resolver_max_lookups=getattr(config, "feedback_resolution_max_lookups", 25),
            resolver_no_key_max_lookups=getattr(config, "feedback_resolution_no_key_max_lookups", 10),
            resolver_time_budget_sec=getattr(config, "feedback_resolution_time_budget_sec", 20),
            resolver_run_cache_enabled=getattr(config, "feedback_resolution_run_cache_enabled", True),
        )
        if feedback_artifacts:
            manifest_path, questionnaire_path = feedback_artifacts
            print(f"   Feedback manifest exported: {manifest_path}")
            print(f"   Feedback questionnaire template exported: {questionnaire_path}")
            try:
                # Same HTML as web/D1: per-paper 👍/👎 links must appear in email too (many clients ignore <script>).
                web_report = inject_feedback_actions_into_report(report, str(manifest_path))
                web_report = append_feedback_fallback_strip(web_report, str(manifest_path))
                try:
                    from paperfeeder.pipeline.summarizer import PaperSummarizer

                    email_summarizer = PaperSummarizer(
                        api_key=getattr(config, "llm_api_key", "") or "",
                        base_url=getattr(config, "llm_base_url", None),
                        model=getattr(config, "llm_model", "claude-3-5-sonnet-20241022"),
                        research_interests=getattr(config, "research_interests", ""),
                        prompt_addon=getattr(config, "prompt_addon", ""),
                        prompt_language=getattr(config, "prompt_language", "zh-CN"),
                        debug_save_pdfs=getattr(config, "debug_save_pdfs", False),
                        debug_pdf_dir=getattr(config, "debug_pdf_dir", "debug_pdfs"),
                        pdf_max_pages=getattr(config, "pdf_max_pages", 10),
                    )
                    email_report = make_email_safe_report_html(
                        email_summarizer.rewrap_existing_report_html(web_report)
                    )
                except Exception as exc:
                    print(f"   Email template rewrap failed, falling back to raw feedback HTML: {exc}")
                    email_report = make_email_safe_report_html(web_report)
                try:
                    publish_feedback_run_to_d1(
                        manifest_path=str(manifest_path),
                        report_html=web_report,
                        account_id=getattr(config, "cloudflare_account_id", ""),
                        api_token=getattr(config, "cloudflare_api_token", ""),
                        database_id=getattr(config, "d1_database_id", ""),
                    )
                    print("   Published web viewer report to D1")
                except Exception as exc:
                    print(f"   D1 run publish failed (non-blocking): {exc}")
            except Exception as exc:
                print(f"   Feedback web-view build failed (non-blocking): {exc}")
        else:
            print("   Feedback manifest: no report-visible papers to export")
    except Exception as exc:
        print(f"   Feedback manifest export failed (non-blocking): {exc}")

    if debug_sample and not debug_write_memory:
        print("   Debug sample: skipped semantic memory update")
    else:
        update_semantic_memory_from_report(final_papers, report, config)

    if dry_run:
        from paperfeeder.email import FileEmailer

        print("Dry run: saving report to file...")
        file_emailer = FileEmailer(DEFAULT_REPORT_PREVIEW_PATH)
        await file_emailer.send(
            to=config.email_to,
            subject=f"Paper Digest - {datetime.now().strftime('%Y-%m-%d')}",
            html_content=email_report,
        )
        print(f"Report saved to {DEFAULT_REPORT_PREVIEW_PATH}")
    else:
        attachment_paths: List[str] = []
        if feedback_artifacts:
            manifest_path, questionnaire_path = (
                str(feedback_artifacts[0]),
                str(feedback_artifacts[1]),
            )
            mode = getattr(config, "feedback_email_attachments", "all")
            attachment_paths = _feedback_email_attachment_paths(
                str(mode), manifest_path, questionnaire_path
            )
        await send_email(email_report, config, attachments=_build_email_attachments(attachment_paths))

    print("\nPipeline complete")
    print(f"   Papers fetched: {len(papers)}")
    print(f"   Blogs fetched: {len(all_blogs)}")
    print(f"   After keyword filter: {len(coarse_filtered) if coarse_filtered else 0}")
    print(f"   After enrichment: {len(enriched_papers) if enriched_papers else 0}")
    print(f"   Final papers: {len(final_papers) if final_papers else 0}")
    print(f"   Total in report: {len(final_papers) + len(all_blogs)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PaperFeeder digest runner")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to config file")
    parser.add_argument("--days", type=int, default=1, help="Days to look back for papers")
    parser.add_argument("--blog-days", type=int, default=7, help="Days to look back for blogs")
    parser.add_argument("--dry-run", action="store_true", help="Don't send email, save to file")
    parser.add_argument("--no-blogs", action="store_true", help="Disable blog fetching")
    parser.add_argument("--no-papers", action="store_true", help="Disable paper fetching")
    parser.add_argument(
        "--debug-sample",
        action="store_true",
        help="Load paper(s) from tests/debug_sample.json (or --debug-sample-path); skip fetch, filters, enrichment",
    )
    parser.add_argument(
        "--debug-sample-path",
        default=None,
        help="JSON file for --debug-sample (default: tests/debug_sample.json, else tests/debug_sample.example.json)",
    )
    parser.add_argument(
        "--debug-minimal-report",
        action="store_true",
        help="Without --debug-sample: still fetch papers but use stub HTML instead of main digest LLM",
    )
    parser.add_argument(
        "--debug-llm-report",
        action="store_true",
        help="With --debug-sample: call main digest LLM for report body (default for debug is stub HTML, no LLM)",
    )
    parser.add_argument(
        "--debug-write-memory",
        action="store_true",
        help="With --debug-sample: still update state/semantic/memory.json (default: skip to avoid polluting)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(
        run_pipeline(
            config_path=args.config,
            days_back=args.days,
            dry_run=args.dry_run,
            no_papers=args.no_papers,
            no_blogs=args.no_blogs,
            debug_sample=args.debug_sample,
            debug_sample_path=args.debug_sample_path,
            debug_minimal_report=args.debug_minimal_report,
            debug_llm_report=args.debug_llm_report,
            debug_write_memory=args.debug_write_memory,
        )
    )

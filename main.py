#!/usr/bin/env python3
"""
Daily Paper Assistant - Main Entry Point
Pipeline: Sources → Filter → Summarize → Email
"""

from __future__ import annotations

import asyncio
import argparse
from datetime import datetime, timedelta
from typing import Optional, List

from sources import ArxivSource, HuggingFaceSource, ManualSource
from filters import KeywordFilter, LLMFilter
from summarizer import PaperSummarizer
from emailer import ResendEmailer
from config import Config
from models import Paper


async def fetch_papers(config: Config, days_back: int = 1) -> List[Paper]:
    """Fetch papers from all sources."""
    papers = []
    
    # arXiv
    print("📚 Fetching from arXiv...")
    arxiv_source = ArxivSource(config.arxiv_categories)
    arxiv_papers = await arxiv_source.fetch(days_back=days_back, max_results=100)  # 减少数量加速
    papers.extend(arxiv_papers)
    print(f"   Found {len(arxiv_papers)} papers")
    
    # Hugging Face Daily Papers
    print("🤗 Fetching from HuggingFace Daily Papers...")
    hf_source = HuggingFaceSource()
    hf_papers = await hf_source.fetch()
    papers.extend(hf_papers)
    print(f"   Found {len(hf_papers)} papers")
    
    # Manual additions (from D1 or local)
    if config.manual_source_enabled:
        print("📝 Fetching manual additions...")
        manual_source = ManualSource(config.manual_source_path)
        manual_papers = await manual_source.fetch()
        papers.extend(manual_papers)
        print(f"   Found {len(manual_papers)} papers")
    
    # Deduplicate by arxiv_id or url
    seen = set()
    unique_papers = []
    for p in papers:
        key = p.arxiv_id or p.url
        if key not in seen:
            seen.add(key)
            unique_papers.append(p)
    
    print(f"✅ Total unique papers: {len(unique_papers)}")
    return unique_papers


async def filter_papers(papers: List[Paper], config: Config) -> List[Paper]:
    """Apply filters to select relevant papers.
    
    Stage 1: Keyword filter (title + abstract)
    Stage 2: LLM filter (title + abstract + authors) - uses cheaper model
    """
    print(f"\n🔍 Filtering {len(papers)} papers...")
    
    # Stage 1: Keyword filter (fast, free) - matches keywords in title + abstract
    keyword_filter = KeywordFilter(
        keywords=config.keywords,
        exclude_keywords=config.exclude_keywords
    )
    filtered = keyword_filter.filter(papers)
    print(f"   ✓ Keyword filter: {len(filtered)} papers (matched title/abstract)")
    
    # Stage 2: LLM filter (uses cheaper model) - evaluates title + abstract + authors
    if config.llm_filter_enabled and len(filtered) > config.llm_filter_threshold:
        # Use filter-specific API key if provided, otherwise use main LLM API key
        filter_api_key = config.llm_filter_api_key
        filter_base_url = config.llm_filter_base_url
        filter_model = config.llm_filter_model
        
        print(f"   🤖 Applying LLM filter ({filter_model} @ {filter_base_url})...")
        llm_filter = LLMFilter(
            api_key=filter_api_key,
            research_interests=config.research_interests,
            base_url=filter_base_url,
            model=filter_model
        )
        filtered = await llm_filter.filter(filtered, max_papers=config.max_papers)
        print(f"   ✓ LLM filter: {len(filtered)} papers selected")
        
        # Show top papers with reasons if available
        if filtered and hasattr(filtered[0], 'filter_reason'):
            print(f"   📌 Top picks:")
            for i, paper in enumerate(filtered, 1):
                reason = getattr(paper, 'filter_reason', '')
                score = getattr(paper, 'relevance_score', 0) * 10
                print(f"      {i}. [{score:.1f}/10] {paper.title[:50]}...")
                if reason:
                    print(f"         → {reason[:60]}...")
    elif config.llm_filter_enabled:
        print(f"   ⏭️  Skipping LLM filter (only {len(filtered)} papers, threshold: {config.llm_filter_threshold})")
    
    # Final limit
    if len(filtered) > config.max_papers:
        filtered = filtered[:config.max_papers]
        print(f"   ✂️  Trimmed to max: {len(filtered)} papers")
    
    return filtered


async def summarize_papers(papers: list[Paper], config: Config) -> str:
    """Generate summary report using LLM."""
    print(f"\n📝 Summarizing {len(papers)} papers...")
    print(f"   Using: {config.llm_model} @ {config.llm_base_url}")
    
    # 从环境变量或配置读取调试选项（可选）
    debug_save_pdfs = getattr(config, 'debug_save_pdfs', False)
    debug_pdf_dir = getattr(config, 'debug_pdf_dir', 'debug_pdfs')
    pdf_max_pages = getattr(config, 'pdf_max_pages', 10)  # 默认只提取前10页
    
    summarizer = PaperSummarizer(
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
        model=config.llm_model,
        research_interests=config.research_interests,
        debug_save_pdfs=debug_save_pdfs,
        debug_pdf_dir=debug_pdf_dir,
        pdf_max_pages=pdf_max_pages
    )
    
    # 使用PDF多模态输入（如果模型支持，更高效且token更少）
    # extract_fulltext配置现在控制是否使用PDF多模态
    report = await summarizer.generate_report(
        papers,
        use_pdf_multimodal=config.extract_fulltext,  # 如果为True，使用PDF多模态
    )
    print("   Summary generated!")
    return report


async def send_email(report: str, config: Config) -> bool:
    """Send the report via email."""
    print(f"\n📧 Sending email to {config.email_to}...")
    
    emailer = ResendEmailer(api_key=config.resend_api_key)
    
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"📚 Daily Paper Digest - {today}"
    
    success = await emailer.send(
        to=config.email_to,
        subject=subject,
        html_content=report
    )
    
    if success:
        print("   Email sent successfully!")
    else:
        print("   ❌ Failed to send email")
    
    return success


async def run_pipeline(config_path: str = "config.yaml", days_back: int = 1, dry_run: bool = False):
    """Run the full pipeline."""
    print("=" * 60)
    print(f"🚀 Daily Paper Assistant - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    # Load config
    config = Config.from_yaml(config_path)
    
    # Fetch
    papers = await fetch_papers(config, days_back=days_back)
    
    if not papers:
        print("\n⚠️ No papers found. Exiting.")
        return
    
    # Filter
    filtered_papers = await filter_papers(papers, config)
    
    if not filtered_papers:
        print("\n⚠️ No papers passed filters. Exiting.")
        return
    
    # Summarize (includes optional full text extraction)
    report = await summarize_papers(filtered_papers, config)
    
    # Output/Send
    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN - Report Preview:")
        print("=" * 60)
        print(report)
        
        # Also save to file
        with open("report_preview.html", "w") as f:
            f.write(report)
        print("\n📄 Report saved to report_preview.html")
    else:
        await send_email(report, config)
    
    print("\n✨ Pipeline complete!")


def main():
    parser = argparse.ArgumentParser(description="Daily Paper Assistant")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--days", type=int, default=1, help="Days to look back")
    parser.add_argument("--dry-run", action="store_true", help="Don't send email, just preview")
    
    args = parser.parse_args()
    
    asyncio.run(run_pipeline(
        config_path=args.config,
        days_back=args.days,
        dry_run=args.dry_run
    ))


if __name__ == "__main__":
    main()

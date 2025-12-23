#!/usr/bin/env python3
"""
Daily Paper Assistant - AI Agent Workflow
Pipeline: Fetch → Keyword Filter (Recall) → LLM Coarse Filter → Research (Enrichment) → LLM Fine Filter (Ranking) → Synthesize
"""

from __future__ import annotations

import asyncio
import argparse
import os
from datetime import datetime, timedelta
from typing import Optional, List

from sources import ArxivSource, HuggingFaceSource, ManualSource
from filters import KeywordFilter, LLMFilter
from researcher import PaperResearcher, MockPaperResearcher
from summarizer import PaperSummarizer
from emailer import ResendEmailer, FileEmailer
from config import Config
from models import Paper


async def fetch_papers(config: Config, days_back: int = 1) -> List[Paper]:
    """Stage 1: Fetch papers from all sources (Recall)."""
    papers = []
    
    # arXiv
    print("📚 Fetching from arXiv...")
    arxiv_source = ArxivSource(config.arxiv_categories)
    arxiv_papers = await arxiv_source.fetch(days_back=days_back, max_results=300)
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


async def filter_papers_coarse(papers: List[Paper], config: Config) -> List[Paper]:
    """
    Stage 2 & 3: Apply filters to select relevant papers.
    
    Stage 2: Keyword filter (Recall) - 保留较多数量，避免漏网之鱼
    Stage 3: LLM Coarse filter - 基于title+abstract粗筛，得到Top 20
    """
    print(f"\n🔍 Filtering {len(papers)} papers...")
    
    # Stage 2: Keyword filter (Recall)
    print("\n--- Stage 2: Keyword Filter (Recall) ---")
    keyword_filter = KeywordFilter(
        keywords=config.keywords,
        exclude_keywords=config.exclude_keywords
    )
    filtered = keyword_filter.filter(papers)
    print(f"   ✅ Keyword filter: {len(filtered)} papers matched (保留较多，避免漏网)")
    
    # Stage 3: LLM Coarse filter (Title + Abstract only)
    print("\n--- Stage 3: LLM Coarse Filter (Title + Abstract) ---")
    if config.llm_filter_enabled and len(filtered) > config.llm_filter_threshold:
        # Use filter-specific API key if provided, otherwise use main LLM API key
        filter_api_key = config.llm_filter_api_key
        filter_base_url = config.llm_filter_base_url
        filter_model = config.llm_filter_model
        
        print(f"   🤖 Applying LLM Coarse Filter ({filter_model})...")
        llm_filter = LLMFilter(
            api_key=filter_api_key,
            research_interests=config.research_interests,
            base_url=filter_base_url,
            model=filter_model
        )
        
        # Coarse filtering: 不包含community signals
        filtered = await llm_filter.filter(
            filtered, 
            max_papers=20,  # 粗筛得到Top 20进入下一阶段
            include_community_signals=False
        )
        print(f"   ✅ LLM Coarse Filter: {len(filtered)} papers selected for enrichment")
        
        # Show top papers
        if filtered:
            print(f"   📌 Top candidates for research:")
            for i, paper in enumerate(filtered[:5], 1):
                score = getattr(paper, 'relevance_score', 0) * 10
                print(f"      {i}. [{score:.1f}/10] {paper.title[:60]}...")
    elif config.llm_filter_enabled:
        print(f"   ⭐️ Skipping LLM Coarse Filter (only {len(filtered)} papers, threshold: {config.llm_filter_threshold})")
    
    return filtered


async def enrich_papers(papers: List[Paper], config: Config) -> List[Paper]:
    """
    Stage 4: Research (Enrichment) - 联网调研，收集社区信号
    """
    print("\n--- Stage 4: Research & Enrichment ---")
    
    # Check if Tavily API key is available
    tavily_api_key = config.tavily_api_key
    
    if not tavily_api_key:
        print("   ⚠️  TAVILY_API_KEY not found, using mock researcher")
        researcher = MockPaperResearcher()
    else:
        print(f"   🔍 Using Tavily API for research")
        researcher = PaperResearcher(
            api_key=tavily_api_key,
            max_concurrent=5,
            search_depth="basic"
        )
    
    # Enrich papers with community signals
    enriched_papers = await researcher.research(papers)
    
    # Show some research results
    print(f"\n   📊 Sample research notes:")
    for i, paper in enumerate(enriched_papers[:3], 1):
        notes = getattr(paper, 'research_notes', 'N/A')
        print(f"      {i}. {paper.title[:50]}...")
        print(f"         🔍 {notes[:100]}...")
    
    return enriched_papers


async def filter_papers_fine(papers: List[Paper], config: Config) -> List[Paper]:
    """
    Stage 5: LLM Fine Filter (Ranking) - 基于content + community signals精筛
    从20篇中选出真正值得深度阅读的Top 3
    """
    print("\n--- Stage 5: LLM Fine Filter (Ranking with Community Signals) ---")
    
    if not config.llm_filter_enabled:
        print("   LLM filter disabled, returning all papers")
        return papers[:config.max_papers]
    
    filter_api_key = config.llm_filter_api_key or config.llm_api_key
    filter_base_url = config.llm_filter_base_url
    filter_model = config.llm_filter_model
    
    print(f"   🤖 Applying LLM Fine Filter with Community Signals ({filter_model})...")
    llm_filter = LLMFilter(
        api_key=filter_api_key,
        research_interests=config.research_interests,
        base_url=filter_base_url,
        model=filter_model
    )
    
    # Fine filtering: 包含community signals
    final_papers = await llm_filter.filter(
        papers,
        max_papers=config.max_papers,  # 精筛得到最终的Top 3
        include_community_signals=True  # 关键: 使用community signals
    )
    print(f"   ✅ LLM Fine Filter: Selected {len(final_papers)} papers for final report")
    
    # Show final selections with reasons
    if final_papers and hasattr(final_papers[0], 'filter_reason'):
        print(f"\n   🏆 Final selections:")
        for i, paper in enumerate(final_papers, 1):
            reason = getattr(paper, 'filter_reason', '')
            score = getattr(paper, 'relevance_score', 0) * 10
            print(f"      {i}. [{score:.1f}/10] {paper.title[:50]}...")
            if reason:
                print(f"         → {reason[:80]}...")
    
    return final_papers


async def summarize_papers(papers: list[Paper], config: Config) -> str:
    """Stage 6: Synthesize - 生成最终报告"""
    print(f"\n--- Stage 6: Synthesis (Report Generation) ---")
    print(f"   📝 Generating report for {len(papers)} papers...")
    print(f"   Using: {config.llm_model} @ {config.llm_base_url}")
    
    # 从环境变量或配置读取调试选项
    debug_save_pdfs = getattr(config, 'debug_save_pdfs', False)
    debug_pdf_dir = getattr(config, 'debug_pdf_dir', 'debug_pdfs')
    pdf_max_pages = getattr(config, 'pdf_max_pages', 10)
    
    summarizer = PaperSummarizer(
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
        model=config.llm_model,
        research_interests=config.research_interests,
        debug_save_pdfs=debug_save_pdfs,
        debug_pdf_dir=debug_pdf_dir,
        pdf_max_pages=pdf_max_pages
    )
    
    # 使用PDF多模态输入（如果模型支持）
    report = await summarizer.generate_report(
        papers,
        use_pdf_multimodal=config.extract_fulltext,
    )
    print("   ✅ Report generated!")
    return report


async def send_email(report: str, config: Config) -> bool:
    """Send the report via email."""
    print(f"\n📧 Sending email to {config.email_to}...")
    
    emailer = ResendEmailer(
        api_key=config.resend_api_key,
        from_email=config.email_from
    )
    
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"📚 Daily Paper Digest - {today}"
    
    success = await emailer.send(
        to=config.email_to,
        subject=subject,
        html_content=report
    )
    
    if success:
        print("   ✅ Email sent successfully!")
    else:
        print("   ❌ Failed to send email")
    
    return success


async def run_pipeline(config_path: str = "config.yaml", days_back: int = 1, dry_run: bool = False):
    """
    Run the full AI Agent pipeline.
    
    Workflow:
    1. Fetch: 获取论文 (arXiv, HuggingFace, Manual)
    2. Keyword Filter (Recall): 关键词匹配，保留较多数量
    3. LLM Coarse Filter: 基于title+abstract粗筛，得到Top 20
    4. Research (Enrichment): 联网调研Top 20，获取社区信号
    5. LLM Fine Filter (Ranking): 基于content+signals精筛，得到Top 3
    6. Synthesize: 生成最终报告
    """
    print("=" * 80)
    print(f"🚀 PaperFeeder AI Agent - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)
    print("\n📋 Workflow: Fetch → Recall → Coarse Filter → Enrich → Fine Filter → Synthesize\n")
    
    # Load config
    config = Config.from_yaml(config_path)
    
    # Stage 1: Fetch (Recall)
    print("=" * 80)
    print("STAGE 1: FETCH (Recall)")
    print("=" * 80)
    papers = await fetch_papers(config, days_back=days_back)
    
    if not papers:
        print("\n⚠️ No papers found. Exiting.")
        return
    
    # Stage 2-3: Keyword Filter + LLM Coarse Filter
    print("\n" + "=" * 80)
    print("STAGE 2-3: FILTERING (Recall → Coarse)")
    print("=" * 80)
    coarse_filtered = await filter_papers_coarse(papers, config)
    
    if not coarse_filtered:
        print("\n⚠️ No papers passed coarse filter. Exiting.")
        return
    
    # Stage 4: Research & Enrichment
    print("\n" + "=" * 80)
    print("STAGE 4: ENRICHMENT (Research)")
    print("=" * 80)
    enriched_papers = await enrich_papers(coarse_filtered, config)
    
    # Stage 5: LLM Fine Filter (Ranking)
    print("\n" + "=" * 80)
    print("STAGE 5: RANKING (Fine Filter with Signals)")
    print("=" * 80)
    final_papers = await filter_papers_fine(enriched_papers, config)
    
    if not final_papers:
        print("\n⚠️ No papers passed fine filter. Exiting.")
        return
    
    # Stage 6: Synthesize
    print("\n" + "=" * 80)
    print("STAGE 6: SYNTHESIS (Report Generation)")
    print("=" * 80)
    report = await summarize_papers(final_papers, config)
    
    # Output/Send
    print("\n" + "=" * 80)
    print("DELIVERY")
    print("=" * 80)
    
    if dry_run:
        print("\n🔍 DRY RUN - Saving report to file...")
        file_emailer = FileEmailer("report_preview.html")
        await file_emailer.send(
            to=config.email_to,
            subject=f"Paper Digest - {datetime.now().strftime('%Y-%m-%d')}",
            html_content=report
        )
        print("✅ Report saved to report_preview.html")
    else:
        await send_email(report, config)
    
    print("\n" + "=" * 80)
    print("✨ Pipeline Complete!")
    print("=" * 80)
    print(f"\n📊 Summary:")
    print(f"   - Papers fetched: {len(papers)}")
    print(f"   - After keyword filter: {len(coarse_filtered)}")
    print(f"   - After enrichment: {len(enriched_papers)}")
    print(f"   - Final selection: {len(final_papers)}")


def main():
    parser = argparse.ArgumentParser(
        description="PaperFeeder AI Agent - Hunt for 'The Next Big Thing'",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Workflow:
  1. Fetch papers from arXiv, HuggingFace, and manual sources
  2. Keyword filter (Recall) - Cast a wide net
  3. LLM Coarse filter - Quick scoring based on title/abstract → Top 20
  4. Research & Enrichment - Gather community signals via Tavily API
  5. LLM Fine filter - Deep ranking with community signals → Top 3
  6. Synthesis - Generate "Editor's Choice" style report

Environment Variables:
  LLM_API_KEY         - Main LLM API key (for summarization)
  LLM_FILTER_API_KEY  - Filter LLM API key (optional, uses cheaper model)
  TAVILY_API_KEY      - Tavily search API key (for research stage)
  RESEND_API_KEY      - Email delivery API key
  EMAIL_TO            - Recipient email address
        """
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--days", type=int, default=1, help="Days to look back")
    parser.add_argument("--dry-run", action="store_true", help="Don't send email, save to file")
    
    args = parser.parse_args()
    
    asyncio.run(run_pipeline(
        config_path=args.config,
        days_back=args.days,
        dry_run=args.dry_run
    ))


if __name__ == "__main__":
    main()
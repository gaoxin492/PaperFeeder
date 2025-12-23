"""
Paper enrichment module using Tavily API for external research.
Searches for community signals: GitHub stars, Reddit/Twitter discussions, reproducibility issues.
"""

from __future__ import annotations

import asyncio
import aiohttp
from typing import List, Optional
from models import Paper


class PaperResearcher:
    """Enrich papers with external community signals using Tavily search."""
    
    TAVILY_API_URL = "https://api.tavily.com/search"
    
    def __init__(
        self,
        api_key: str,
        max_concurrent: int = 5,  # 并发控制
        search_depth: str = "basic",  # "basic" or "advanced"
    ):
        self.api_key = api_key
        self.max_concurrent = max_concurrent
        self.search_depth = search_depth
    
    async def research(self, papers: List[Paper]) -> List[Paper]:
        """
        对论文列表进行并发的外部调研。
        
        Args:
            papers: 待调研的论文列表
            
        Returns:
            enriched papers with research_notes filled
        """
        if not papers:
            return papers
        
        print(f"\n🔍 Researching {len(papers)} papers for external signals...")
        
        # 创建信号量控制并发
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def research_one(paper: Paper, idx: int) -> Paper:
            async with semaphore:
                print(f"   [{idx+1}/{len(papers)}] Researching: {paper.title[:50]}...")
                research_notes = await self._search_paper(paper)
                paper.research_notes = research_notes
                return paper
        
        # 并发执行所有搜索
        tasks = [research_one(paper, i) for i, paper in enumerate(papers)]
        enriched_papers = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤掉异常
        successful = []
        failed_count = 0
        for result in enriched_papers:
            if isinstance(result, Exception):
                print(f"   ⚠️ Research failed: {result}")
                failed_count += 1
            else:
                successful.append(result)
        
        if failed_count > 0:
            print(f"   ⚠️ {failed_count} papers failed to research")
        
        print(f"   ✅ Research complete: {len(successful)} papers enriched")
        return successful
    
    async def _search_paper(self, paper: Paper) -> str:
        """
        搜索单篇论文的外部信号。
        
        Strategy:
        - 只搜外部评价，不搜论文全文
        - 关注: GitHub stars, Reddit/Twitter讨论, 复现问题
        """
        # 构建搜索query - 关注外部评价而非论文本身
        query = self._build_search_query(paper)
        
        # 调用Tavily API
        try:
            notes = await self._call_tavily(query)
            return notes or "No external signals found."
        except Exception as e:
            print(f"      ⚠️ Search failed: {e}")
            return f"Search failed: {str(e)[:100]}"
    
    def _build_search_query(self, paper: Paper) -> str:
        """
        构建搜索query，聚焦外部评价。
        
        Examples:
        - "Diffusion Language Models site:github.com OR site:reddit.com review discussion"
        - "RLHF alignment site:twitter.com OR site:huggingface.co"
        """
        # 提取论文标题的关键词（去掉冠词等）
        title = paper.title
        
        # 添加site限制，只搜索特定平台
        query = f'"{title}" (site:github.com OR site:reddit.com OR site:twitter.com OR site:huggingface.co) (review OR discussion OR implementation OR reproducibility)'
        
        return query
    
    async def _call_tavily(self, query: str) -> Optional[str]:
        """
        调用Tavily API进行搜索。
        
        Returns:
            3-sentence summary of external signals
        """
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": self.search_depth,
            "max_results": 5,  # 只要top 5结果
            "include_answer": True,  # 让Tavily生成摘要
            "include_raw_content": False,  # 不需要原始内容
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.TAVILY_API_URL, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"      ⚠️ Tavily API error: {response.status} - {error_text[:100]}")
                        return None
                    
                    data = await response.json()
                    
                    # 优先使用Tavily的answer（AI生成的摘要）
                    if data.get("answer"):
                        return self._format_tavily_answer(data["answer"])
                    
                    # 否则从results中提取关键信息
                    results = data.get("results", [])
                    if not results:
                        return None
                    
                    return self._format_tavily_results(results)
                    
        except asyncio.TimeoutError:
            print(f"      ⚠️ Tavily timeout")
            return None
        except Exception as e:
            print(f"      ⚠️ Tavily error: {type(e).__name__}: {e}")
            return None
    
    def _format_tavily_answer(self, answer: str) -> str:
        """
        格式化Tavily的AI生成摘要。
        限制在3句话以内。
        """
        sentences = answer.split('. ')
        # 取前3句
        summary = '. '.join(sentences[:3])
        if not summary.endswith('.'):
            summary += '.'
        return summary
    
    def _format_tavily_results(self, results: List[dict]) -> str:
        """
        从Tavily搜索结果中提取关键信号。
        
        Focus:
        - GitHub repo stars
        - Reddit/Twitter热议
        - 复现问题
        """
        signals = []
        
        for result in results[:3]:  # 只看前3个结果
            title = result.get("title", "")
            url = result.get("url", "")
            content = result.get("content", "")
            
            # 检测GitHub repo
            if "github.com" in url and content:
                # 尝试提取star数（如果在content中）
                import re
                star_match = re.search(r'(\d+[\d,]*)\s*stars?', content, re.IGNORECASE)
                if star_match:
                    stars = star_match.group(1)
                    signals.append(f"GitHub repo with {stars} stars")
                else:
                    signals.append("GitHub implementation available")
            
            # 检测社区讨论
            elif "reddit.com" in url or "twitter.com" in url:
                platform = "Reddit" if "reddit.com" in url else "Twitter"
                # 提取讨论要点（取content前100字符）
                snippet = content[:100].strip()
                if snippet:
                    signals.append(f"{platform} discussion: {snippet}...")
            
            # 检测HuggingFace
            elif "huggingface.co" in url:
                signals.append(f"HuggingFace: {title[:60]}")
        
        if not signals:
            return "No significant external signals found."
        
        # 组合成3句话以内的summary
        if len(signals) == 1:
            return signals[0] + "."
        elif len(signals) == 2:
            return f"{signals[0]}. {signals[1]}."
        else:
            return f"{signals[0]}. {signals[1]}. {signals[2]}."


# Mock researcher for testing without API key
class MockPaperResearcher:
    """Mock researcher that generates fake research notes."""
    
    async def research(self, papers: List[Paper]) -> List[Paper]:
        print(f"\n🔍 Mock research for {len(papers)} papers...")
        
        for i, paper in enumerate(papers, 1):
            print(f"   [{i}/{len(papers)}] Mock researching: {paper.title[:50]}...")
            # 生成假的research notes
            paper.research_notes = f"Mock: GitHub repo with ~500 stars. Some discussion on Reddit about methodology."
            await asyncio.sleep(0.1)  # 模拟网络延迟
        
        print(f"   ✅ Mock research complete")
        return papers
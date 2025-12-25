"""
Paper source fetchers.
Each source implements fetch() -> list[Paper]
"""

from __future__ import annotations

import asyncio
import aiohttp
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional, List
import re

from models import Paper, Author, PaperSource
from .base import BaseSource


class ArxivSource(BaseSource):
    """Fetch papers from arXiv API."""
    
    BASE_URL = "http://export.arxiv.org/api/query"
    
    def __init__(self, categories: list[str]):
        self.categories = categories
    
    async def fetch(self, days_back: int = 1, max_results: int = 200) -> List[Paper]:
        """Fetch recent papers from specified categories."""
        papers = []
        
        # Build category query
        cat_query = " OR ".join([f"cat:{cat}" for cat in self.categories])
        
        # arXiv API parameters
        params = {
            "search_query": cat_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        
        print(f"      Querying: {cat_query[:60]}...")
        print(f"      (arXiv API can be slow, ~10-60s, please wait...)")
        
        # 重试机制
        max_retries = 3
        xml_content = None
        
        for attempt in range(max_retries):
            try:
                # 增加超时到 120 秒，分别设置连接超时和读取超时
                timeout = aiohttp.ClientTimeout(
                    total=120,      # 总超时
                    connect=30,     # 连接超时
                    sock_read=90    # 读取超时
                )
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(self.BASE_URL, params=params) as response:
                        if response.status != 200:
                            print(f"      ❌ arXiv API error: {response.status}")
                            return papers
                        
                        print(f"      ✓ Response received, reading data...")
                        xml_content = await response.text()
                        print(f"      ✓ Got {len(xml_content)} bytes, parsing XML...")
                        break  # 成功，退出重试循环
                        
            except asyncio.TimeoutError:
                print(f"      ⚠️ Timeout on attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    print(f"      Retrying in 5 seconds...")
                    await asyncio.sleep(5)
                else:
                    print(f"      ❌ All retries failed. arXiv may be overloaded.")
                    return papers
            except asyncio.CancelledError:
                print(f"      ❌ Request cancelled")
                return papers
            except Exception as e:
                print(f"      ❌ Request failed: {type(e).__name__}: {e}")
                if attempt < max_retries - 1:
                    print(f"      Retrying in 5 seconds...")
                    await asyncio.sleep(5)
                else:
                    return papers
        
        if not xml_content:
            return papers
        
        # Parse XML response
        root = ET.fromstring(xml_content)
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        for entry in root.findall("atom:entry", ns):
            try:
                # Parse date
                published_str = entry.find("atom:published", ns).text
                published_date = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                
                # Skip if too old
                if published_date.replace(tzinfo=None) < cutoff_date:
                    continue
                
                # Extract arxiv ID from URL
                arxiv_url = entry.find("atom:id", ns).text
                arxiv_id = arxiv_url.split("/abs/")[-1]
                
                # Extract authors
                authors = []
                for author_elem in entry.findall("atom:author", ns):
                    name = author_elem.find("atom:name", ns).text
                    affiliation_elem = author_elem.find("arxiv:affiliation", ns)
                    affiliation = affiliation_elem.text if affiliation_elem is not None else None
                    authors.append(Author(name=name, affiliation=affiliation))
                
                # Extract categories
                categories = []
                for cat_elem in entry.findall("atom:category", ns):
                    categories.append(cat_elem.get("term"))
                
                # Find PDF link
                pdf_url = None
                for link in entry.findall("atom:link", ns):
                    if link.get("title") == "pdf":
                        pdf_url = link.get("href")
                        break
                
                paper = Paper(
                    title=entry.find("atom:title", ns).text.replace("\n", " ").strip(),
                    abstract=entry.find("atom:summary", ns).text.replace("\n", " ").strip(),
                    url=arxiv_url,
                    source=PaperSource.ARXIV,
                    arxiv_id=arxiv_id,
                    authors=authors,
                    published_date=published_date,
                    categories=categories,
                    pdf_url=pdf_url,
                )
                papers.append(paper)
                
            except Exception as e:
                print(f"Error parsing arXiv entry: {e}")
                continue
        
        return papers


class HuggingFaceSource(BaseSource):
    """Fetch papers from Hugging Face Daily Papers."""
    
    # HF Daily Papers API endpoint (可用镜像)
    API_URLS = [
        "https://huggingface.co/api/daily_papers",           # 官方
        "https://hf-mirror.com/api/daily_papers",            # 国内镜像
    ]
    
    def __init__(self, use_mirror: bool = True):
        self.use_mirror = use_mirror
    
    async def fetch(self, date: Optional[str] = None) -> List[Paper]:
        """Fetch today's papers from HuggingFace."""
        papers = []
        
        # 选择 URL
        urls_to_try = self.API_URLS if self.use_mirror else [self.API_URLS[0]]
        
        data = None
        for base_url in urls_to_try:
            url = base_url
            if date:
                url = f"{base_url}?date={date}"
            
            print(f"      Trying: {base_url}...")
            
            try:
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            print(f"      ❌ HTTP {response.status}, trying next...")
                            continue
                        
                        print(f"      ✓ Response received, parsing...")
                        data = await response.json()
                        break  # 成功
                        
            except asyncio.TimeoutError:
                print(f"      ⚠️ Timeout, trying next...")
                continue
            except Exception as e:
                print(f"      ⚠️ {type(e).__name__}: {e}")
                continue
        
        if data is None:
            print(f"      ❌ All sources failed.")
            return papers
        
        for item in data:
            try:
                paper_data = item.get("paper", {})
                
                # Extract arxiv ID if available
                arxiv_id = paper_data.get("id")
                arxiv_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None
                
                # Parse authors
                authors = []
                for author in paper_data.get("authors", []):
                    authors.append(Author(name=author.get("name", "")))
                
                # Parse date
                published_str = paper_data.get("publishedAt")
                published_date = None
                if published_str:
                    published_date = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                
                paper = Paper(
                    title=paper_data.get("title", ""),
                    abstract=paper_data.get("summary", ""),
                    url=arxiv_url or f"https://huggingface.co/papers/{arxiv_id}",
                    source=PaperSource.HUGGINGFACE,
                    arxiv_id=arxiv_id,
                    authors=authors,
                    published_date=published_date,
                    pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else None,
                )
                papers.append(paper)
                
            except Exception as e:
                print(f"Error parsing HuggingFace paper: {e}")
                continue
        
        return papers


class ManualSource(BaseSource):
    """Fetch manually added papers from local JSON or D1 database."""
    
    def __init__(self, source_path: str):
        """
        source_path can be:
        - A local JSON file path
        - A D1 database identifier (for future implementation)
        """
        self.source_path = source_path
    
    async def fetch(self) -> List[Paper]:
        """Fetch papers from manual source."""
        # For MVP: read from local JSON file
        if self.source_path.endswith(".json"):
            return await self._fetch_from_json()
        else:
            # Future: implement D1 fetching
            return await self._fetch_from_d1()
    
    async def _fetch_from_json(self) -> List[Paper]:
        """Read papers from local JSON file."""
        papers = []
        
        try:
            with open(self.source_path, "r") as f:
                data = json.load(f)
            
            for item in data.get("papers", []):
                # Support both full paper objects and simple URLs
                if isinstance(item, str):
                    # Just a URL - need to fetch metadata
                    paper = await self._fetch_paper_metadata(item)
                    if paper:
                        papers.append(paper)
                else:
                    # Full paper object
                    paper = Paper.from_dict(item)
                    papers.append(paper)
                    
        except FileNotFoundError:
            print(f"Manual papers file not found: {self.source_path}")
        except Exception as e:
            print(f"Error reading manual papers: {e}")
        
        return papers
    
    async def _fetch_from_d1(self) -> List[Paper]:
        """Fetch papers from Cloudflare D1 database."""
        # TODO: Implement D1 fetching
        # This will be used when integrating with the chatbot
        print("D1 fetching not yet implemented")
        return []
    
    async def _fetch_paper_metadata(self, url: str) -> Optional[Paper]:
        """Fetch paper metadata from URL (arxiv, openreview, etc.)."""
        # Extract arxiv ID from URL
        arxiv_match = re.search(r"arxiv.org/(?:abs|pdf)/(\d+\.\d+)", url)
        if arxiv_match:
            arxiv_id = arxiv_match.group(1)
            return await self._fetch_arxiv_paper(arxiv_id)
        
        # For other URLs, create a basic paper object
        return Paper(
            title="[Metadata not fetched]",
            abstract="",
            url=url,
            source=PaperSource.MANUAL,
            notes="Manually added - metadata needs to be fetched",
        )
    
    async def _fetch_arxiv_paper(self, arxiv_id: str) -> Optional[Paper]:
        """Fetch a single paper from arXiv by ID."""
        url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                xml_content = await response.text()
        
        root = ET.fromstring(xml_content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        
        try:
            authors = []
            for author_elem in entry.findall("atom:author", ns):
                name = author_elem.find("atom:name", ns).text
                authors.append(Author(name=name))
            
            return Paper(
                title=entry.find("atom:title", ns).text.replace("\n", " ").strip(),
                abstract=entry.find("atom:summary", ns).text.replace("\n", " ").strip(),
                url=f"https://arxiv.org/abs/{arxiv_id}",
                source=PaperSource.MANUAL,
                arxiv_id=arxiv_id,
                authors=authors,
                pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            )
        except Exception as e:
            print(f"Error parsing arXiv paper {arxiv_id}: {e}")
            return None


# For future expansion
class SemanticScholarSource(BaseSource):
    """Fetch papers from Semantic Scholar API."""
    
    async def fetch(self, **kwargs) -> List[Paper]:
        # TODO: Implement
        return []


class OpenReviewSource(BaseSource):
    """Fetch papers from OpenReview."""
    
    async def fetch(self, **kwargs) -> List[Paper]:
        # TODO: Implement
        return []

"""
Configuration management for the paper assistant.
Updated: Added blog source configuration support.
"""

from __future__ import annotations

import os
import yaml
from dotenv import load_dotenv

# 自动加载 .env 文件
load_dotenv()
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class Config:
    # LLM settings (通用配置，支持任意 OpenAI 兼容 API)
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    
    # 常用预设:
    # OpenAI:    base_url="https://api.openai.com/v1", model="gpt-4o-mini"
    # Claude:    base_url="https://api.anthropic.com/v1", model="claude-sonnet-4-20250514"
    # DeepSeek:  base_url="https://api.deepseek.com/v1", model="deepseek-chat"
    # Gemini:    base_url="https://generativelanguage.googleapis.com/v1beta/openai", model="gemini-2.0-flash"
    # Qwen:      base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", model="qwen-turbo"
    # Local:     base_url="http://localhost:11434/v1", model="llama3"
    
    # Email settings
    resend_api_key: str = ""
    email_to: str = ""
    email_from: str = "paperfeeder@resend.dev"
    
    # arXiv settings (fewer categories = faster queries)
    arxiv_categories: list[str] = field(default_factory=lambda: [
        "cs.LG",   # Machine Learning
        "cs.CL",   # Computation and Language  
        # "cs.CV",   # Computer Vision - 可选，取消注释来启用
        # "cs.AI",   # Artificial Intelligence - 可选
        # "stat.ML", # Statistics - Machine Learning - 可选
    ])
    
    # Keywords for filtering (title + abstract)
    keywords: list[str] = field(default_factory=lambda: [
        # Generative models
        "diffusion model", "diffusion language", "flow matching",
        "generative model", "autoregressive",
        # LLM reasoning
        "chain of thought", "reasoning", "llm", "large language model",
        "in-context learning", "prompt",
        # Representation learning
        "representation learning", "contrastive learning", 
        "self-supervised", "foundation model",
        # AI Safety
        "ai safety", "alignment", "rlhf", "red teaming",
        "jailbreak", "safety benchmark", "harmful",
        # Specific interests
        "tokenizer", "tokenization", "continuous token",
        "latent space", "latent reasoning",
    ])
    
    exclude_keywords: list[str] = field(default_factory=lambda: [
        # Exclude if you want
    ])
    
    # Research interests description (for LLM filtering/summarization)
    research_interests: str = """
    I'm a Master's student researching:
    1. Generative models, especially diffusion models for language
    2. LLM reasoning, including chain-of-thought and latent reasoning
    3. Representation learning and continuous tokenization
    4. AI safety, including benchmarks and alignment
    
    I'm particularly interested in papers that:
    - Bridge generation and representation learning
    - Propose new reasoning paradigms for LLMs
    - Introduce novel safety evaluation methods
    - Have strong mathematical foundations
    """
    
    # Filtering settings
    llm_filter_enabled: bool = True   # Enable LLM-based filtering (recommended)
    llm_filter_threshold: int = 5     # Only use LLM filter if > N papers after keyword filter
    max_papers: int = 20              # Max papers in final report
    
    # LLM Filter settings (use cheaper model for filtering)
    llm_filter_api_key: str = ""      # API key for filter LLM
    llm_filter_base_url: str = "https://api.openai.com/v1"  # Base URL for filter LLM
    llm_filter_model: str = "gpt-4o-mini"  # Cheaper model for filtering (e.g., gpt-4o-mini, gpt-3.5-turbo)

    tavily_api_key: str = ""
    
    # PDF Multimodal Input (more efficient than text extraction)
    extract_fulltext: bool = True     # Use PDF multimodal input (direct PDF to model, saves tokens)
                                      # If True and model supports (Claude/Gemini), sends PDF directly
                                      # If False, only uses abstract
    fulltext_top_n: int = 5           # Deprecated, kept for compatibility
    pdf_max_pages: int = 10           # Maximum pages to extract from PDF (0 = all pages, default: 10)
                                      # Only first N pages are sent to LLM to save tokens
    
    # Source enablement settings
    papers_enabled: bool = True            # Enable fetching from paper sources (arXiv, HF, Manual)
    manual_source_enabled: bool = True
    manual_source_path: str = "manual_papers.json"  # Or D1 connection string
    
    # =============================================================================
    # Blog Source Settings (NEW!)
    # =============================================================================
    blogs_enabled: bool = True        # Enable blog fetching from RSS feeds
    blog_days_back: int = 1           # How many days back to look for blog posts
    
    # Which blogs to enable (if None, uses all priority blogs)
    # Available keys: openai, anthropic, deepmind, google_ai, meta_ai,
    #                 bair, stanford_ai, karpathy, lilianweng, colah,
    #                 jay_alammar, distill, fastai, the_gradient,
    #                 nvidia_ai, microsoft_research, aws_ml,
    #                 alignment_forum, lesswrong_ai
    enabled_blogs: Optional[List[str]] = None
    
    # Custom blogs (add your own RSS feeds)
    # Format: {"key": {"name": "...", "feed_url": "...", "priority": True/False}}
    custom_blogs: Optional[Dict[str, Dict[str, Any]]] = None
    
    # D1 settings (for future chatbot integration)
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    d1_database_id: str = ""
    
    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """Load config from YAML file, with env var overrides."""
        config_data = {}
        
        if os.path.exists(path):
            with open(path, "r") as f:
                config_data = yaml.safe_load(f) or {}
        
        # Environment variable overrides (for GitHub Actions secrets)
        env_overrides = {
            "llm_api_key": os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"),
            "llm_base_url": os.getenv("LLM_BASE_URL"),
            "llm_model": os.getenv("LLM_MODEL"),
            "llm_filter_api_key": os.getenv("LLM_FILTER_API_KEY"),
            "llm_filter_base_url": os.getenv("LLM_FILTER_BASE_URL"),
            "llm_filter_model": os.getenv("LLM_FILTER_MODEL"),
            "resend_api_key": os.getenv("RESEND_API_KEY"),
            "email_to": os.getenv("EMAIL_TO"),
            "tavily_api_key": os.getenv("TAVILY_API_KEY"),
            "cloudflare_account_id": os.getenv("CLOUDFLARE_ACCOUNT_ID"),
            "cloudflare_api_token": os.getenv("CLOUDFLARE_API_TOKEN"),
            "d1_database_id": os.getenv("D1_DATABASE_ID"),
            # Source enablement
            "papers_enabled": os.getenv("PAPERS_ENABLED"),
            # Blog settings from environment
            "blogs_enabled": os.getenv("BLOGS_ENABLED"),
            "blog_days_back": os.getenv("BLOG_DAYS_BACK"),
        }
        
        # Apply environment variable overrides (only if value is not None)
        for key, value in env_overrides.items():
            if value is not None:
                # Handle boolean conversion for source enablement
                if key in ("blogs_enabled", "papers_enabled"):
                    config_data[key] = value.lower() not in ("false", "0", "no", "off")
                # Handle int conversion for blog_days_back
                elif key == "blog_days_back":
                    try:
                        config_data[key] = int(value)
                    except ValueError:
                        pass
                else:
                    config_data[key] = value
        
        # Auto-detect base_url based on model if not explicitly set
        if config_data.get("llm_filter_model") and not config_data.get("llm_filter_base_url"):
            model = config_data["llm_filter_model"].lower()
            if "deepseek" in model:
                config_data["llm_filter_base_url"] = "https://api.deepseek.com/v1"
            elif "claude" in model:
                config_data["llm_filter_base_url"] = "https://api.anthropic.com/v1"
            elif "gemini" in model:
                config_data["llm_filter_base_url"] = "https://generativelanguage.googleapis.com/v1beta/openai"
            elif "qwen" in model:
                config_data["llm_filter_base_url"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        
        return cls(**config_data)
    
    def to_yaml(self, path: str):
        """Save config to YAML file."""
        data = {
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "email_to": self.email_to,
            "email_from": self.email_from,
            "arxiv_categories": self.arxiv_categories,
            "keywords": self.keywords,
            "exclude_keywords": self.exclude_keywords,
            "research_interests": self.research_interests,
            "llm_filter_enabled": self.llm_filter_enabled,
            "llm_filter_threshold": self.llm_filter_threshold,
            "max_papers": self.max_papers,
            "llm_filter_api_key": self.llm_filter_api_key,
            "llm_filter_base_url": self.llm_filter_base_url,
            "llm_filter_model": self.llm_filter_model,
            "extract_fulltext": self.extract_fulltext,
            "fulltext_top_n": self.fulltext_top_n,
            "pdf_max_pages": getattr(self, 'pdf_max_pages', 10),
            "papers_enabled": self.papers_enabled,
            "manual_source_enabled": self.manual_source_enabled,
            "manual_source_path": self.manual_source_path,
            # Blog settings
            "blogs_enabled": self.blogs_enabled,
            "blog_days_back": self.blog_days_back,
            "enabled_blogs": self.enabled_blogs,
            "custom_blogs": self.custom_blogs,
        }
        
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def create_default_config(path: str = "config.yaml"):
    """Create a default config file."""
    config = Config()
    config.to_yaml(path)
    print(f"Created default config at {path}")
    print("Please edit it and add your API keys as environment variables.")
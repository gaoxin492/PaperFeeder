"""
Configuration schema and loader for the reorganized package.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover - import-time fallback for lightweight environments
    yaml = None

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - import-time fallback for lightweight environments
    def load_dotenv(*_args, **_kwargs):
        return False

from .paths import (
    DEFAULT_PROMPT_ADDON_PATH,
    DEFAULT_RESEARCH_PROFILE_PATH,
    DEFAULT_SEMANTIC_MEMORY_PATH,
    DEFAULT_SEMANTIC_SEEDS_PATH,
    DEFAULT_USER_ARXIV_CATEGORIES_PATH,
    DEFAULT_USER_BLOG_SETTINGS_PATH,
    DEFAULT_USER_EXCLUDE_KEYWORDS_PATH,
    DEFAULT_USER_KEYWORDS_PATH,
)

_cwd_dotenv = Path.cwd() / ".env"
if _cwd_dotenv.exists():
    load_dotenv(dotenv_path=_cwd_dotenv)


def _parse_loose_bool(value: Any, *, default: bool) -> bool:
    """
    Coerce YAML/env-style values to bool.

    YAML may load quoted "false" as a string, which is truthy in Python and would
    incorrectly keep features enabled.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):  # py3: bool is int subclass
        return value != 0
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped in ("", "default"):
            return default
        return stripped not in ("false", "0", "no", "off")
    return bool(value)


def _load_user_list_file(path_value: str | None) -> list[str]:
    if not path_value:
        return []

    file_path = Path(path_value)
    if not file_path.exists():
        return []

    items: list[str] = []
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line:
            items.append(line)
    return items


@dataclass
class Config:
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    resend_api_key: str = ""
    email_to: str = ""
    email_from: str = "paperfeeder@resend.dev"

    arxiv_categories: list[str] = field(default_factory=lambda: ["cs.LG", "cs.CL"])
    keywords: list[str] = field(
        default_factory=lambda: [
            "machine learning",
            "language model",
            "reasoning",
        ]
    )
    exclude_keywords: list[str] = field(default_factory=list)
    research_interests: str = "You are screening AI research updates. Prefer technically substantive work with clear novelty."
    prompt_addon: str = ""
    prompt_language: str = "zh-CN"
    user_blog_settings_path: str = DEFAULT_USER_BLOG_SETTINGS_PATH
    user_research_profile_path: str = DEFAULT_RESEARCH_PROFILE_PATH
    user_prompt_addon_path: str = DEFAULT_PROMPT_ADDON_PATH
    user_arxiv_categories_path: str = DEFAULT_USER_ARXIV_CATEGORIES_PATH
    user_keywords_path: str = DEFAULT_USER_KEYWORDS_PATH
    user_exclude_keywords_path: str = DEFAULT_USER_EXCLUDE_KEYWORDS_PATH

    llm_filter_enabled: bool = True
    llm_filter_threshold: int = 5
    max_papers: int = 20

    llm_filter_api_key: str = ""
    llm_filter_base_url: str = "https://api.openai.com/v1"
    llm_filter_model: str = "gpt-4o-mini"
    tavily_api_key: str = ""

    extract_fulltext: bool = True
    fulltext_top_n: int = 5
    pdf_max_pages: int = 10

    papers_enabled: bool = True
    manual_source_enabled: bool = True
    manual_source_path: str = "manual_papers.json"
    semantic_scholar_enabled: bool = False
    semantic_scholar_api_key: str = ""
    semantic_scholar_max_results: int = 30
    semantic_state_backend: str = "file"
    semantic_scholar_seeds_path: str = DEFAULT_SEMANTIC_SEEDS_PATH
    semantic_memory_enabled: bool = True
    semantic_memory_path: str = DEFAULT_SEMANTIC_MEMORY_PATH
    semantic_seen_ttl_days: int = 30
    semantic_memory_max_ids: int = 5000

    blogs_enabled: bool = True
    blog_days_back: int = 1
    max_blog_posts: int = 5
    enabled_blogs: Optional[List[str]] = None
    custom_blogs: Optional[Dict[str, Dict[str, Any]]] = field(default_factory=dict)

    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    d1_database_id: str = ""

    feedback_endpoint_base_url: str = ""
    feedback_link_signing_secret: str = ""
    # When False, email/HTML omits the “Open Feedback Web Viewer” banner (inline 👍/👎 still work).
    feedback_web_viewer_link_in_email: bool = True
    # Email attachments from feedback export: all | manifest | none (see runner).
    feedback_email_attachments: str = "all"
    feedback_token_ttl_days: int = 7
    feedback_reviewer: str = ""
    feedback_resolution_enabled: bool = True
    feedback_resolution_timeout_sec: int = 8
    feedback_resolution_max_lookups: int = 25
    feedback_resolution_no_key_max_lookups: int = 10
    feedback_resolution_time_budget_sec: int = 20
    feedback_resolution_run_cache_enabled: bool = True

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        if yaml is None:
            raise ImportError("PyYAML is required to load configuration files")
        config_data = {}
        if os.path.exists(path):
            with open(path, "r") as handle:
                config_data = yaml.safe_load(handle) or {}

        user_blog_settings_path = (
            os.getenv("USER_BLOG_SETTINGS_PATH")
            or config_data.get("user_blog_settings_path")
            or DEFAULT_USER_BLOG_SETTINGS_PATH
        )
        if user_blog_settings_path and os.path.exists(user_blog_settings_path):
            with open(user_blog_settings_path, "r") as handle:
                blog_data = yaml.safe_load(handle) or {}
                if isinstance(blog_data, dict):
                    config_data.update(blog_data)

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
            "feedback_endpoint_base_url": os.getenv("FEEDBACK_ENDPOINT_BASE_URL"),
            "feedback_link_signing_secret": os.getenv("FEEDBACK_LINK_SIGNING_SECRET"),
            "feedback_web_viewer_link_in_email": os.getenv("FEEDBACK_WEB_VIEWER_LINK_IN_EMAIL"),
            "feedback_email_attachments": os.getenv("FEEDBACK_EMAIL_ATTACHMENTS"),
            "feedback_token_ttl_days": os.getenv("FEEDBACK_TOKEN_TTL_DAYS"),
            "feedback_reviewer": os.getenv("FEEDBACK_REVIEWER"),
            "feedback_resolution_enabled": os.getenv("FEEDBACK_RESOLUTION_ENABLED"),
            "feedback_resolution_timeout_sec": os.getenv("FEEDBACK_RESOLUTION_TIMEOUT_SEC"),
            "feedback_resolution_max_lookups": os.getenv("FEEDBACK_RESOLUTION_MAX_LOOKUPS"),
            "feedback_resolution_no_key_max_lookups": os.getenv("FEEDBACK_RESOLUTION_NO_KEY_MAX_LOOKUPS"),
            "feedback_resolution_time_budget_sec": os.getenv("FEEDBACK_RESOLUTION_TIME_BUDGET_SEC"),
            "feedback_resolution_run_cache_enabled": os.getenv("FEEDBACK_RESOLUTION_RUN_CACHE_ENABLED"),
            "user_blog_settings_path": os.getenv("USER_BLOG_SETTINGS_PATH"),
            "prompt_language": os.getenv("PROMPT_LANGUAGE"),
            "user_research_profile_path": os.getenv("USER_RESEARCH_PROFILE_PATH"),
            "user_prompt_addon_path": os.getenv("USER_PROMPT_ADDON_PATH"),
            "user_arxiv_categories_path": os.getenv("USER_ARXIV_CATEGORIES_PATH"),
            "user_keywords_path": os.getenv("USER_KEYWORDS_PATH"),
            "user_exclude_keywords_path": os.getenv("USER_EXCLUDE_KEYWORDS_PATH"),
            "papers_enabled": os.getenv("PAPERS_ENABLED"),
            "semantic_scholar_enabled": os.getenv("SEMANTIC_SCHOLAR_ENABLED"),
            "semantic_scholar_api_key": os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
            "semantic_scholar_max_results": os.getenv("SEMANTIC_SCHOLAR_MAX_RESULTS"),
            "semantic_state_backend": os.getenv("SEMANTIC_STATE_BACKEND"),
            "semantic_scholar_seeds_path": os.getenv("SEMANTIC_SCHOLAR_SEEDS_PATH"),
            "semantic_memory_enabled": os.getenv("SEMANTIC_MEMORY_ENABLED"),
            "semantic_memory_path": os.getenv("SEMANTIC_MEMORY_PATH"),
            "semantic_seen_ttl_days": os.getenv("SEMANTIC_SEEN_TTL_DAYS"),
            "semantic_memory_max_ids": os.getenv("SEMANTIC_MEMORY_MAX_IDS"),
            "blogs_enabled": os.getenv("BLOGS_ENABLED"),
            "blog_days_back": os.getenv("BLOG_DAYS_BACK"),
            "max_blog_posts": os.getenv("MAX_BLOG_POSTS"),
        }

        for key, value in env_overrides.items():
            if value is None:
                continue
            if key in (
                "blogs_enabled",
                "papers_enabled",
                "semantic_scholar_enabled",
                "semantic_memory_enabled",
                "feedback_resolution_enabled",
                "feedback_resolution_run_cache_enabled",
                "feedback_web_viewer_link_in_email",
            ):
                config_data[key] = value.lower() not in ("false", "0", "no", "off")
            elif key in (
                "blog_days_back",
                "max_blog_posts",
                "semantic_scholar_max_results",
                "semantic_seen_ttl_days",
                "semantic_memory_max_ids",
                "feedback_token_ttl_days",
                "feedback_resolution_timeout_sec",
                "feedback_resolution_max_lookups",
                "feedback_resolution_no_key_max_lookups",
                "feedback_resolution_time_budget_sec",
            ):
                try:
                    config_data[key] = int(value)
                except ValueError:
                    pass
            else:
                config_data[key] = value

        research_profile_path = config_data.get("user_research_profile_path") or DEFAULT_RESEARCH_PROFILE_PATH
        if research_profile_path:
            profile_file = Path(research_profile_path)
            if profile_file.exists():
                profile_text = profile_file.read_text().strip()
                if profile_text:
                    config_data["research_interests"] = profile_text

        prompt_addon_path = config_data.get("user_prompt_addon_path") or DEFAULT_PROMPT_ADDON_PATH
        if prompt_addon_path:
            addon_file = Path(prompt_addon_path)
            if addon_file.exists():
                addon_text = addon_file.read_text(encoding="utf-8").strip()
                if addon_text:
                    config_data["prompt_addon"] = addon_text

        arxiv_categories = _load_user_list_file(
            config_data.get("user_arxiv_categories_path") or DEFAULT_USER_ARXIV_CATEGORIES_PATH
        )
        if arxiv_categories:
            config_data["arxiv_categories"] = arxiv_categories

        keywords = _load_user_list_file(
            config_data.get("user_keywords_path") or DEFAULT_USER_KEYWORDS_PATH
        )
        if keywords:
            config_data["keywords"] = keywords

        exclude_keywords = _load_user_list_file(
            config_data.get("user_exclude_keywords_path") or DEFAULT_USER_EXCLUDE_KEYWORDS_PATH
        )
        if exclude_keywords:
            config_data["exclude_keywords"] = exclude_keywords

        if not config_data.get("semantic_scholar_seeds_path"):
            old_seeds = Path("semantic_scholar_seeds.json")
            if old_seeds.exists():
                config_data["semantic_scholar_seeds_path"] = str(old_seeds)
        if not config_data.get("semantic_memory_path"):
            old_memory = Path("semantic_scholar_memory.json")
            if old_memory.exists():
                config_data["semantic_memory_path"] = str(old_memory)

        if "feedback_web_viewer_link_in_email" in config_data:
            config_data["feedback_web_viewer_link_in_email"] = _parse_loose_bool(
                config_data.get("feedback_web_viewer_link_in_email"), default=True
            )
        if config_data.get("feedback_email_attachments") is not None:
            normalized = str(config_data["feedback_email_attachments"]).strip().lower()
            config_data["feedback_email_attachments"] = normalized if normalized else "all"

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
        if yaml is None:
            raise ImportError("PyYAML is required to write configuration files")
        data = {
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "email_to": self.email_to,
            "email_from": self.email_from,
            "arxiv_categories": self.arxiv_categories,
            "keywords": self.keywords,
            "exclude_keywords": self.exclude_keywords,
            "research_interests": self.research_interests,
            "prompt_addon": self.prompt_addon,
            "prompt_language": self.prompt_language,
            "user_blog_settings_path": self.user_blog_settings_path,
            "user_research_profile_path": self.user_research_profile_path,
            "user_prompt_addon_path": self.user_prompt_addon_path,
            "user_arxiv_categories_path": self.user_arxiv_categories_path,
            "user_keywords_path": self.user_keywords_path,
            "user_exclude_keywords_path": self.user_exclude_keywords_path,
            "llm_filter_enabled": self.llm_filter_enabled,
            "llm_filter_threshold": self.llm_filter_threshold,
            "max_papers": self.max_papers,
            "llm_filter_api_key": self.llm_filter_api_key,
            "llm_filter_base_url": self.llm_filter_base_url,
            "llm_filter_model": self.llm_filter_model,
            "extract_fulltext": self.extract_fulltext,
            "fulltext_top_n": self.fulltext_top_n,
            "pdf_max_pages": self.pdf_max_pages,
            "papers_enabled": self.papers_enabled,
            "manual_source_enabled": self.manual_source_enabled,
            "manual_source_path": self.manual_source_path,
            "semantic_scholar_enabled": self.semantic_scholar_enabled,
            "semantic_scholar_max_results": self.semantic_scholar_max_results,
            "semantic_scholar_seeds_path": self.semantic_scholar_seeds_path,
            "semantic_memory_enabled": self.semantic_memory_enabled,
            "semantic_memory_path": self.semantic_memory_path,
            "semantic_seen_ttl_days": self.semantic_seen_ttl_days,
            "semantic_memory_max_ids": self.semantic_memory_max_ids,
            "blogs_enabled": self.blogs_enabled,
            "blog_days_back": self.blog_days_back,
            "enabled_blogs": self.enabled_blogs,
            "custom_blogs": self.custom_blogs,
            "feedback_endpoint_base_url": self.feedback_endpoint_base_url,
            "feedback_web_viewer_link_in_email": self.feedback_web_viewer_link_in_email,
            "feedback_email_attachments": self.feedback_email_attachments,
            "feedback_token_ttl_days": self.feedback_token_ttl_days,
            "feedback_reviewer": self.feedback_reviewer,
            "feedback_resolution_enabled": self.feedback_resolution_enabled,
            "feedback_resolution_timeout_sec": self.feedback_resolution_timeout_sec,
            "feedback_resolution_max_lookups": self.feedback_resolution_max_lookups,
            "feedback_resolution_no_key_max_lookups": self.feedback_resolution_no_key_max_lookups,
            "feedback_resolution_time_budget_sec": self.feedback_resolution_time_budget_sec,
            "feedback_resolution_run_cache_enabled": self.feedback_resolution_run_cache_enabled,
        }
        with open(path, "w") as handle:
            yaml.dump(data, handle, default_flow_style=False, allow_unicode=True)


def create_default_config(path: str = "config.yaml"):
    config = Config()
    config.to_yaml(path)
    print(f"Created default config at {path}")
    print("Please edit it and add your API keys as environment variables.")


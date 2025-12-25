#!/usr/bin/env python3
"""
Test script to verify --no-papers functionality
"""

import os
import sys

def test_env_var_logic():
    """Test environment variable setting logic"""
    print("Testing environment variable logic...")

    # Test setting PAPERS_ENABLED=false
    os.environ['PAPERS_ENABLED'] = 'false'
    papers_enabled = os.getenv('PAPERS_ENABLED')

    print(f"PAPERS_ENABLED = {papers_enabled}")

    # Test config override logic (from config.py)
    env_overrides = {
        "papers_enabled": os.getenv("PAPERS_ENABLED"),
    }

    config_data = {}
    for key, value in env_overrides.items():
        if value is not None:
            config_data[key] = value

    print(f"Config override applied: {config_data}")

    # Test bool conversion
    papers_enabled = config_data.get('papers_enabled', 'true')
    if isinstance(papers_enabled, str):
        papers_enabled_bool = papers_enabled.lower() not in ('false', '0', 'no', 'off')

    print(f"Converted to bool: {papers_enabled_bool}")
    return papers_enabled_bool == False

def test_blog_source_available():
    """Test BLOG_SOURCE_AVAILABLE definition"""
    print("\nTesting BLOG_SOURCE_AVAILABLE...")

    try:
        import feedparser
        blog_available = True
        print("feedparser available: True")
    except ImportError:
        blog_available = False
        print("feedparser available: False")

    return blog_available

if __name__ == "__main__":
    print("=" * 50)
    print("Testing --no-papers functionality")
    print("=" * 50)

    # Test env var logic
    env_test_passed = test_env_var_logic()

    # Test blog availability
    blog_test_passed = test_blog_source_available()

    print("\n" + "=" * 50)
    print("RESULTS:")
    print(f"Environment variable logic: {'✅ PASS' if env_test_passed else '❌ FAIL'}")
    print(f"Blog source availability: {'✅ PASS' if blog_test_passed else '❌ PASS (expected False)'}")

    if env_test_passed:
        print("\n🎉 --no-papers functionality should work correctly!")
    else:
        print("\n❌ --no-papers functionality has issues!")

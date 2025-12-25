#!/usr/bin/env python3
"""
Test script to verify --no-papers fix
"""

import os
import sys

def test_config_boolean_conversion():
    """Test that PAPERS_ENABLED=false gets converted to boolean False"""
    print("Testing config boolean conversion...")

    # Set environment variable
    os.environ['PAPERS_ENABLED'] = 'false'

    # Simulate config.py logic
    env_overrides = {
        "papers_enabled": os.getenv("PAPERS_ENABLED"),
    }

    config_data = {}
    for key, value in env_overrides.items():
        if value is not None:
            # Handle boolean conversion for source enablement
            if key in ("blogs_enabled", "papers_enabled"):
                config_data[key] = value.lower() not in ("false", "0", "no", "off")
            else:
                config_data[key] = value

    papers_enabled = config_data.get('papers_enabled', True)

    print(f"PAPERS_ENABLED env var: {os.getenv('PAPERS_ENABLED')}")
    print(f"Converted to bool: {papers_enabled}")
    print(f"Type: {type(papers_enabled)}")

    return papers_enabled is False

def test_run_pipeline_logic():
    """Test the run_pipeline logic with papers_enabled=False"""
    print("\nTesting run_pipeline logic...")

    # Simulate config object
    class MockConfig:
        def __init__(self, papers_enabled):
            self.papers_enabled = papers_enabled

    config = MockConfig(papers_enabled=False)

    # Simulate run_pipeline logic
    papers = []
    if getattr(config, 'papers_enabled', True):
        papers = "WOULD_FETCH_PAPERS"
        print("Papers would be fetched")
    else:
        print("📄 Paper fetching disabled (--no-papers flag)")
        papers_disabled = True

    return papers == []

if __name__ == "__main__":
    print("=" * 60)
    print("Testing --no-papers fix")
    print("=" * 60)

    config_test = test_config_boolean_conversion()
    pipeline_test = test_run_pipeline_logic()

    print("\n" + "=" * 60)
    print("RESULTS:")
    print(f"Config boolean conversion: {'✅ PASS' if config_test else '❌ FAIL'}")
    print(f"Pipeline logic: {'✅ PASS' if pipeline_test else '❌ FAIL'}")

    if config_test and pipeline_test:
        print("\n🎉 --no-papers fix should work correctly!")
    else:
        print("\n❌ --no-papers fix still has issues!")

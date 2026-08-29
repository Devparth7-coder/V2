"""
VayuSutra APIx - Rate Limiter Unit Tests
Verifies Token-Bucket throughput, capacity burst enforcement, and ethical jitter behavior.
"""

import time
import pytest
from vayusutra_apix.scrapers.base_scraper import EthicalRateLimiter, UserAgentRotator, RobotsChecker


def test_token_bucket_initial_capacity():
    """Verify rate limiter initializes with full burst capacity."""
    limiter = EthicalRateLimiter(rate_limit_rps=2.0, burst_capacity=3.0, min_jitter_sec=0.0, max_jitter_sec=0.0)
    assert limiter.get_token_count() == pytest.approx(3.0, rel=1e-2)


def test_token_bucket_rate_enforcement():
    """Verify that acquiring tokens throttles calls when tokens are depleted."""
    limiter = EthicalRateLimiter(rate_limit_rps=5.0, burst_capacity=2.0, min_jitter_sec=0.01, max_jitter_sec=0.02)
    
    start = time.monotonic()
    # Consume 4 tokens (2 instant from burst, next 2 require 2/5 = 0.4s + jitter)
    for _ in range(4):
        limiter.acquire(1.0)
    elapsed = time.monotonic() - start
    
    # Expected elapsed >= 0.40 seconds
    assert elapsed >= 0.35, f"Elapsed {elapsed:.3f}s was lower than expected rate limit constraint"


def test_token_bucket_jitter():
    """Verify jitter is added within the configured boundaries."""
    min_j = 0.05
    max_j = 0.10
    limiter = EthicalRateLimiter(rate_limit_rps=100.0, burst_capacity=10.0, min_jitter_sec=min_j, max_jitter_sec=max_j)
    
    start = time.monotonic()
    slept = limiter.acquire(1.0)
    elapsed = time.monotonic() - start
    
    assert elapsed >= min_j * 0.90
    assert slept >= min_j * 0.90


def test_user_agent_rotator():
    """Verify user agent rotator returns modern browser strings with rich headers."""
    ua = UserAgentRotator.get_random_user_agent()
    assert isinstance(ua, str)
    assert len(ua) > 20
    assert ("Mozilla" in ua) or ("Chrome" in ua)

    headers = UserAgentRotator.get_browser_headers()
    assert "User-Agent" in headers
    assert "Accept-Language" in headers
    assert "Sec-Fetch-Mode" in headers


def test_robots_checker_fallback():
    """Verify robots checker allows crawling if domain is unreachable or non-existent."""
    checker = RobotsChecker()
    url = "https://nonexistent-test-airline-subdomain.in/flights"
    # Should fall back to permissive without raising uncaught exceptions
    assert checker.is_allowed(url) is True

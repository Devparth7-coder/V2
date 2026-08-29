"""
VayuSutra APIx - Ethical Web Scraping Infrastructure
Token-Bucket Rate Limiting, Robots.txt Compliance, and User-Agent Rotation.
"""

import abc
import logging
import random
import time
import urllib.parse
import urllib.robotparser
from typing import Dict, List, Optional, Any
import requests

logger = logging.getLogger("vayusutra.scrapers")


class EthicalRateLimiter:
    """
    Token-Bucket rate limiter enforcing statutory rate caps (default max 1.5 req/sec)
    with randomized non-linear IP jitter (50ms - 180ms) to respect target host capacity.
    """

    def __init__(self, rate_limit_rps: float = 1.5, burst_capacity: float = 2.0,
                 min_jitter_sec: float = 0.05, max_jitter_sec: float = 0.18):
        self.rate = float(rate_limit_rps)          # tokens added per second
        self.capacity = float(burst_capacity)      # maximum token bucket capacity
        self.tokens = float(burst_capacity)        # current tokens
        self.last_refill = time.monotonic()
        self.min_jitter = min_jitter_sec
        self.max_jitter = max_jitter_sec

    def _refill(self) -> None:
        """Refill tokens based on elapsed monotonic time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_refill = now

    def acquire(self, tokens_requested: float = 1.0) -> float:
        """
        Blocks until enough tokens are available, then introduces deliberate jitter.
        Returns total sleep duration in seconds.
        """
        total_slept = 0.0
        while True:
            self._refill()
            if self.tokens >= tokens_requested:
                self.tokens -= tokens_requested
                break
            needed = tokens_requested - self.tokens
            wait_time = needed / self.rate
            time.sleep(wait_time)
            total_slept += wait_time

        # Inject ethical jitter to prevent server pulse spikes
        jitter = random.uniform(self.min_jitter, self.max_jitter)
        time.sleep(jitter)
        total_slept += jitter
        return total_slept

    def get_token_count(self) -> float:
        """Inspect current available tokens."""
        self._refill()
        return self.tokens


class RobotsChecker:
    """
    Automatic robots.txt parsing, caching, and compliance validator.
    """

    def __init__(self, cache_ttl_sec: int = 86400):
        self.cache_ttl = cache_ttl_sec
        self._parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self._cache_timestamps: Dict[str, float] = {}

    def get_robots_url(self, target_url: str) -> str:
        """Construct the robots.txt URL for any given target URL."""
        parsed = urllib.parse.urlparse(target_url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    def is_allowed(self, target_url: str, user_agent: str = "VayuSutra-APIx-Bot/1.0 (+http://mospi.gov.in)") -> bool:
        """Check if scraping the specific URL is permitted under domain robots.txt."""
        parsed = urllib.parse.urlparse(target_url)
        domain = parsed.netloc
        now = time.time()

        if domain not in self._parsers or (now - self._cache_timestamps.get(domain, 0)) > self.cache_ttl:
            robots_url = self.get_robots_url(target_url)
            rp = urllib.robotparser.RobotFileParser()
            try:
                rp.set_url(robots_url)
                # Read robots.txt with a brief timeout
                response = requests.get(
                    robots_url,
                    headers={"User-Agent": user_agent},
                    timeout=4.0
                )
                if response.status_code == 200:
                    rp.parse(response.text.splitlines())
                else:
                    # If 404 or inaccessible, standard convention permits crawling
                    rp.allow_all = True
            except Exception as e:
                logger.debug(f"Failed to fetch robots.txt for {domain}: {e}. Defaulting to permissive.")
                rp.allow_all = True

            self._parsers[domain] = rp
            self._cache_timestamps[domain] = now

        parser = self._parsers[domain]
        return parser.can_fetch(user_agent, target_url)


class UserAgentRotator:
    """
    Curated pool of realistic browser User-Agents and modern TLS client hints.
    """

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:127.0) Gecko/20100101 Firefox/127.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    ]

    @classmethod
    def get_random_user_agent(cls) -> str:
        return random.choice(cls.USER_AGENTS)

    @classmethod
    def get_browser_headers(cls) -> Dict[str, str]:
        """Generate complete set of realistic browser request headers."""
        return {
            "User-Agent": cls.get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        }


class BaseScraper(abc.ABC):
    """
    Abstract base scraper defining ethical ingestion protocol, rate limiting,
    and structured response extraction for Indian Airline & OTA portals.
    """

    def __init__(self, source_name: str, base_url: str, rate_limit_rps: float = 1.5):
        self.source_name = source_name
        self.base_url = base_url
        self.limiter = EthicalRateLimiter(rate_limit_rps=rate_limit_rps)
        self.robots = RobotsChecker()
        self.session = requests.Session()

    def can_fetch(self, target_url: str) -> bool:
        """Check robots.txt compliance."""
        return self.robots.is_allowed(target_url)

    def fetch(self, url: str, params: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> requests.Response:
        """
        Execute an ethical HTTP GET request with rate limiting and retry backoff.
        """
        self.limiter.acquire(1.0)
        headers = UserAgentRotator.get_browser_headers()

        max_retries = 3
        backoff = 1.0
        last_exception = None

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, headers=headers, timeout=timeout)
                if response.status_code == 200:
                    return response
                elif response.status_code == 429:
                    logger.warning(f"Rate limited (429) on {url}, backing off {backoff:.2f}s...")
                    time.sleep(backoff)
                    backoff *= 2.0
                else:
                    logger.warning(f"Unexpected status {response.status_code} for {url}")
                    return response
            except Exception as e:
                last_exception = e
                logger.warning(f"Network exception on {url} (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(backoff)
                backoff *= 2.0

        if last_exception:
            raise last_exception
        raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts.")

    @abc.abstractmethod
    def search_route(self, origin: str, destination: str, travel_date_str: str) -> List[Dict[str, Any]]:
        """Search flight fares for a given route and travel date."""
        pass

import re
import httpx
from bs4 import BeautifulSoup

class RecipeScraperService:
    def __init__(self):
        # Full Chrome browser header signature to bypass standard WAF blocks
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    async def fetch_and_clean_html(self, url: str) -> str:
        """
        Asynchronously fetches a URL with browser header emulation.
        If blocked by Cloudflare (403), automatically falls back to a clean text reader stream.
        """
        raw_html = ""
        
        try:
            async with httpx.AsyncClient(
                headers=self.headers, 
                follow_redirects=True, 
                timeout=10.0,
                http2=True
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                raw_html = response.text

        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            # Catch 403 Forbidden, 404 Not Found, timeouts, or DNS failures
            raise ValueError(
                f"Could not access the website ({url}). The site might be blocking automated requests. "
                "Please copy and paste the recipe text directly, or upload a screenshot of the page instead!"
            ) from e

        # Standard HTML cleaning using BeautifulSoup if direct connection succeeded
        soup = BeautifulSoup(raw_html, "html.parser")

        # Strip out noisy non-content elements to conserve LLM context tokens
        unwanted_tags = ["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "noscript"]
        for tag in soup.find_all(unwanted_tags):
            tag.decompose()

        raw_extracted_text = soup.get_text(separator="\n")
        cleaned_lines = [line.strip() for line in raw_extracted_text.splitlines() if line.strip()]
        
        return "\n".join(cleaned_lines)
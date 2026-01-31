import scrapy
import trafilatura
from urllib.parse import urlparse
from oin_crawler.utils.pdf import extract_pdf_text
from oin_crawler.utils.lang import safe_detect


class CompanySitemapSpider(scrapy.Spider):
    name = "company_sitemap"
    custom_settings = {
        "CLOSESPIDER_PAGECOUNT": 10,
        "DEPTH_LIMIT": 2,
        "DOWNLOAD_DELAY": 0.5,
        "ROBOTSTXT_OBEY": True,
    }

    def __init__(self, domain=None, start_url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # akzeptiere Parameter von -a UND bereits gesetzte Attribute
        if start_url:
            self.start_url = start_url
        if domain:
            self.domain = domain

        if not getattr(self, "domain", None) and getattr(self, "start_url", None):
            self.domain = self.start_url.split("/")[2]

        # allowed_domains nur setzen, wenn domain da ist
        if getattr(self, "domain", None):
            self.allowed_domains = [self.domain]

        # falls jemand start_urls per -a gesetzt hat, respektieren; sonst leer lassen
        if not hasattr(self, "start_urls"):
            self.start_urls = []

    def start_requests(self):
        # Priorität: explizites start_url > erstes in start_urls > Domain
        url = getattr(self, "start_url", None) or (self.start_urls[0] if self.start_urls else None)
        if not url and getattr(self, "domain", None):
            url = f"https://{self.domain}"
        if not url:
            raise ValueError("Bitte -a domain=beispiel.com oder -a start_url=https://www.beispiel.com angeben")

        yield scrapy.Request(
            url,
            callback=self.parse,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; OIN/0.1; +contact@example.org)",
                "Referer": f"https://{self.domain}/",
            },
        )

    def parse(self, response):
        # PDF-Erkennung
        ctype = response.headers.get("Content-Type", b"").decode("utf-8", "ignore")
        if "application/pdf" in ctype or response.url.lower().endswith(".pdf"):
            text = extract_pdf_text(response.body)
            lang = safe_detect(text)
            yield {
                "source_url": response.url,
                "source_domain": self.domain,
                "source_type": "pdf",
                "title": response.url.rsplit("/", 1)[-1],
                "text": text[:1_000_000],
                "raw_html": None,
                "mime_type": "application/pdf",
                "lang": lang,
                "content_hash": None,
                "status_code": response.status,
                "published_at": None,
                "crawl_ts": self.crawler.stats.get_value("start_time").isoformat() if self.crawler.stats.get_value("start_time") else None,
                "meta": {"via": "direct"},
            }
            return

        # HTML-Inhalte verarbeiten
        html_text = trafilatura.extract(response.text, include_comments=False) or ""
        if not html_text.strip():
            html_text = " ".join(response.xpath("//body//text()[normalize-space()]").getall())

        lang = safe_detect(html_text)

        yield {
            "source_url": response.url,
            "source_domain": self.domain,
            "source_type": "html",
            "title": response.xpath("//title/text()").get(),
            "text": html_text[:1_000_000],
            "raw_html": response.text,
            "mime_type": response.headers.get("Content-Type", b"text/html").decode("utf-8", "ignore"),
            "lang": lang,
            "content_hash": None,
            "status_code": response.status,
            "published_at": None,
            "crawl_ts": self.crawler.stats.get_value("start_time").isoformat() if self.crawler.stats.get_value("start_time") else None,
            "meta": {"via": "direct"},
        }

        # internen Links folgen
        for href in response.css("a::attr(href)").getall():
            if href.startswith("mailto:") or href.startswith("javascript:"):
                continue
            url = response.urljoin(href)
            if urlparse(url).netloc and self.domain not in urlparse(url).netloc:
                continue
            yield response.follow(url, callback=self.parse)

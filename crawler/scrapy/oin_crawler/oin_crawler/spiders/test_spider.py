import scrapy

class TestSpider(scrapy.Spider):
    name = "test_spider"
    start_urls = ["https://example.org"]

    def parse(self, response):
        self.logger.debug(f"Status: {response.status}")
        self.logger.debug(f"Title: {response.css('title::text').get()}")
        yield {
            "source_url": response.url,
            "source_domain": "example.org",
            "source_type": "html",
            "title": response.css("title::text").get(),
            "text": response.text,
            "raw_html": response.text,
            "mime_type": "text/html",
            "lang": "en",
            "status_code": response.status,
            "published_at": None,
            "meta": {},
        }

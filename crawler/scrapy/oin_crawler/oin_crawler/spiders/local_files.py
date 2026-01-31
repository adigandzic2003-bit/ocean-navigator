import os
import scrapy


class LocalFilesSpider(scrapy.Spider):
    name = "local_files"

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "DOWNLOAD_DELAY": 0,
        "CONCURRENT_REQUESTS": 1,
        "LOG_LEVEL": "INFO",
    }

    def __init__(self, input_dir=None, source="local_folder", *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not input_dir:
            raise ValueError("input_dir fehlt. Beispiel: -a input_dir=tests/corpus/rwe")
        self.input_dir = input_dir
        self.source = source

    def start_requests(self):
        exts = {".txt", ".html", ".htm"}
        for root, _, files in os.walk(self.input_dir):
            for fn in sorted(files):
                ext = os.path.splitext(fn)[1].lower()
                if ext not in exts:
                    continue
                path = os.path.join(root, fn)
                yield scrapy.Request(
                    url="file://" + os.path.abspath(path),
                    callback=self.parse_file,
                    dont_filter=True,
                    meta={"path": path, "filename": fn, "ext": ext},
                )

    def parse_file(self, response):
        fn = response.meta["filename"]
        ext = response.meta["ext"]
        text = (response.text or "").strip()

        yield {
            "source_url": response.url,
            "source_domain": self.source,   # landet als payload.source
            "source_type": "file",
            "title": fn,
            "text": text,
            "raw_html": text if ext in {".html", ".htm"} else None,
            "mime_type": "text/plain" if ext == ".txt" else "text/html",
            "lang": None,
            "status_code": 200,
            "published_at": None,
            "meta": {
                "filename": fn,
                "ext": ext,
                "ingested_from": self.input_dir,
            },
        }

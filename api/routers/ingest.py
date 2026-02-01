cur.execute(
    """
    INSERT INTO oin.oin_master (
        record_type,
        source_type,
        source_id,
        crawler_name,
        status,
        raw_text,
        extracted_from_url,
        content_hash,
        language,
        topic_tags,
        keywords
    )
    VALUES (
        'doc',
        'file',
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s
    )
    """,
    (
        payload.url,                        # source_id
        'scrapy',                           # crawler_name
        payload.status,                     # status
        payload.text,                       # raw_text
        payload.url,                        # extracted_from_url
        payload.metadata.get("content_hash"),
        payload.metadata.get("lang"),
        payload.metadata.get("topic_tags"),
        payload.metadata.get("keywords"),
    )
)

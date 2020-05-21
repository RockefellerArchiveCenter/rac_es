from elasticsearch_dsl import analyzer

base_analyzer = analyzer(
    'base_analyzer',
    tokenizer="standard",
    filter=["lowercase", "stop", "snowball"],
    char_filter=["html_strip"]
)

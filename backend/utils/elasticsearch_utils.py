from elasticsearch import Elasticsearch, helpers, ApiError
from core.config import settings
from core.logger import logger
from time import sleep
from core.exceptions import ElasticsearchException

index_name = settings.ELASTICSEARCH_INDEX_NAME
MAX_RETRIES = 10
RETRY_DELAY = 5

def get_elasticsearch():
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            es = Elasticsearch(
                hosts=[{
                    "host": settings.ELASTICSEARCH_HOST,
                    "port": settings.ELASTICSEARCH_PORT,
                    "scheme": "http"
                }],
                request_timeout=30,      # сек.
                max_retries=3,           # число попыток на каждый запрос
                retry_on_timeout=True    # повторять при таймауте
            )

            # проверяем состояние кластера
            health = es.cluster.health(
                wait_for_status="yellow",
                timeout="30s",          # серверный таймаут сбора статуса
                master_timeout="30s"    # таймаут ожидания ответа мастера
            )
            status = health["status"]
            logger.info(f"Cluster health: {status}")
            if status in ("yellow", "green"):
                return es
            else:
                logger.info(f"Connecting to Elasticsearch failed (attempt {attempt}/{MAX_RETRIES})")
                raise ConnectionError(f"Cluster health is {status}")

        except Exception as e:
            logger.warning(f"Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY * attempt
                logger.info(f"Sleeping {delay}s before next try…")
                sleep(delay)
            else:
                msg = f"Could not connect after {MAX_RETRIES} attempts: {e}"
                logger.error(msg)
                raise ElasticsearchException(msg)

def create_reelearn_index(delete_if_exist=True):
    try:
        es = get_elasticsearch()
        if es.indices.exists(index=index_name):
            if delete_if_exist:
                logger.info(f"Deleting existing index {index_name}")
                es.indices.delete(index=index_name)
            else:
                logger.info(f"Index {index_name} already exists.")
                return

        mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "index.max_ngram_diff": 18,
                "analysis": {
                    "tokenizer": {
                        "ngram_tokenizer": {
                            "type": "ngram",
                            "min_gram": 2,
                            "max_gram": 20,
                            "token_chars": ["letter", "digit"]
                        }
                    },
                    "filter": {
                        "english_stop": {
                            "type": "stop",
                            "stopwords": "_english_"
                        },
                        "english_stemmer": {
                            "type": "stemmer",
                            "language": "english"
                        },
                        "russian_stop": {
                            "type": "stop",
                            "stopwords": "_russian_"
                        },
                        "russian_stemmer": {
                            "type": "stemmer",
                            "language": "russian"
                        },
                        "my_phonetic": {
                            "type": "phonetic",
                            "encoder": "metaphone",
                            "replace": False
                        }
                    },
                    "analyzer": {
                        "en_fuzzy": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": [
                                "lowercase",
                                "english_stop",
                                "english_stemmer",
                                "my_phonetic"
                            ]
                        },
                        "ru_fuzzy": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": [
                                "lowercase",
                                "russian_stop",
                                "russian_stemmer",
                                "my_phonetic"
                            ]
                        },
                        "ngram_analyzer": {
                            "type": "custom",
                            "tokenizer": "ngram_tokenizer",
                            "filter": ["lowercase"]
                        },
                        "whitespace_lowercase": {
                            "type": "custom",
                            "tokenizer": "whitespace",
                            "filter": ["lowercase"]
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "fragment_id": {"type": "long"},
                    "video_id": {"type": "long"},
                    "text": {
                        "type": "text",
                        "analyzer": "standard",
                        "fields": {
                            "en_fuzzy": {
                                "type": "text",
                                "analyzer": "en_fuzzy",
                                "search_analyzer": "standard"
                            },
                            "ru_fuzzy": {
                                "type": "text",
                                "analyzer": "ru_fuzzy",
                                "search_analyzer": "standard"
                            },
                            "ngram": {
                                "type": "text",
                                "analyzer": "ngram_analyzer",
                                "search_analyzer": "whitespace_lowercase"
                            },
                            "keyword": {"type": "keyword", "ignore_above": 256}
                        }
                    },
                    "language": {"type": "keyword"},
                    "timecode_start": {"type": "float"},
                    "timecode_end": {"type": "float"},
                    "tags": {"type": "keyword"},
                    "s3_url": {"type": "keyword"},
                    "speech_confidence": {"type": "float"},
                    "no_speech_prob": {"type": "float"}
                }
            }
        }

        resp = es.indices.create(index=index_name, body=mapping)
        logger.info(f"Index {index_name} created successfully: {resp}")
    except ElasticsearchException as e:
        logger.error(f"Elasticsearch connection error: {str(e)}")
        raise
    except ApiError as e:
        logger.error(f"Elasticsearch API error: {str(e.body)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating index: {str(e)}")
        raise

def convert_fragment(frag):
    return {
        "_index": index_name,
        "_id": str(frag.id),
        "_source": {
            "fragment_id": frag.id,
            "video_id": frag.video_id,
            "text": frag.text,
            "timecode_start": frag.timecode_start,
            "timecode_end": frag.timecode_end,
            "tags": frag.tags or [],
            "s3_url": frag.s3_url,
            "speech_confidence": getattr(frag, "speech_confidence", 1.0),
            "no_speech_prob": getattr(frag, "no_speech_prob", 0.0),
            "language": getattr(frag, "language", "unknown")
        }
    }

def add_new_fragment(frag):
    es = get_elasticsearch()
    doc = convert_fragment(frag)
    es.index(index=index_name, id=doc["_id"], body=doc["_source"])

def delete_fragment_by_id(fragment_id):
    es = get_elasticsearch()
    es.delete(index=index_name, id=str(fragment_id), ignore=[404])

def replace_all_fragments(fragments):
    if not fragments:
        return
    create_reelearn_index(delete_if_exist=True)
    actions = [convert_fragment(frag) for frag in fragments]
    helpers.bulk(get_elasticsearch(), actions)

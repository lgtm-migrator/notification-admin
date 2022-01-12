from flask_caching import Cache
from notifications_utils.clients.antivirus.antivirus_client import AntivirusClient
from notifications_utils.clients.redis.redis_client import RedisClient
from notifications_utils.clients.statsd.statsd_client import StatsdClient
from notifications_utils.clients.zendesk.zendesk_client import ZendeskClient
import os

antivirus_client = AntivirusClient()
statsd_client = StatsdClient()
zendesk_client = ZendeskClient()
redis_client = RedisClient()

cache = Cache(config={
    "CACHE_TYPE": os.environ.get("FLASK_CACHE_TYPE", "SimpleCache"),
    "CACHE_DEFAULT_TIMEOUT": os.environ.get("FLASK_CACHE_DEFAULT_TIMEOUT", 300),
    "CACHE_REDIS_HOST": os.environ.get("FLASK_CACHE_REDIS_HOST", "redis") # ignored if SimpleCache
})

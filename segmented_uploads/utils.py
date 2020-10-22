from django.conf import settings
from django.core.cache import caches


cache_redis = caches[getattr(settings, 'UPLOADS_CACHE_LOCK_REDIS_NAME', 'default')]

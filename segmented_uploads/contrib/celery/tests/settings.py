from segmented_uploads.tests.settings import *

INSTALLED_APPS = INSTALLED_APPS + ['segmented_uploads.contrib.celery']
UPLOADS_MATERIALIZE_SYNCHRONOUSLY = False

CELERY_BROKER_URL = 'redis://%s/0' % REDIS_LOCATION
CELERY_RESULT_BACKEND = 'redis://%s/2' % REDIS_LOCATION

ROOT_URLCONF = 'segmented_uploads.contrib.celery.tests.urls'

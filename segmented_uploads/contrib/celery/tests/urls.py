from django.urls import include, path

urlpatterns = [
    path('task-status/', include('segmented_uploads.contrib.celery.urls')),
    path('', include('segmented_uploads.tests.urls')),
]

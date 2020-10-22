from django.conf.urls import url

from . import views


urlpatterns = [
    url(
        r'^task/materialization/(?P<id>[\w-]+)/$',
        views.UploadMaterializationStatusView.as_view(),
        name='celery-materialization-status',
    ),
]

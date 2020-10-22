from celery.result import AsyncResult
from django.http import HttpResponse
from django.urls import reverse

from segmented_uploads.views import UploadView


class UploadMaterializationStatusView(UploadView):
    def post(self, request, id):
        if AsyncResult(id).ready():
            return HttpResponse(reverse('segmented-upload-endpoint'), status=300)
        return HttpResponse('')

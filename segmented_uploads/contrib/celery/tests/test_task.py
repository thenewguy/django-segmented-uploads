from unittest.mock import patch

from celery.result import AsyncResult
from django.core.files.base import ContentFile
from django.urls import resolve
from multimedia.tests.base import CeleryTestCase
from segmented_uploads.models import Upload, UploadSegment

from .celery import app as celery_app
from ..models import queue_materialize
from ..tasks import materialize, purge


class UploadTests(CeleryTestCase):
    CELERY_APP = celery_app
    
    def test_materialize_task_result(self):
        for algo in ('', 'md5', 'sha1'):
            with self.subTest(algorithm=algo):
                upload = Upload.objects.create(token=f'some-token-{algo}', session='some-session')
                segment = UploadSegment.objects.create(index=1, file=ContentFile(b'bar', name='bar.txt'), upload=upload)
                result = materialize.delay(upload.pk, algo)
                self.await_result_ready(result)
                upload.refresh_from_db()
                actual = upload.file.read()
                self.assertEqual(actual, b'bar')
        
    
    def test_upload_materialize(self):
        upload = Upload.objects.create(token='some-token', session='some-session')
        segment = UploadSegment.objects.create(index=1, file=ContentFile(b'baz', name='baz.txt'), upload=upload)
        
        # https://docs.djangoproject.com/en/3.0/topics/signals/#sending-signals
        # response from signal.send() is [(receiver, response), ... ]
        result = None
        send_response = upload.materialize()
        for receiver, result in send_response:
            if receiver is queue_materialize:
                break
        
        self.assertIs(receiver, queue_materialize)
        self.assertIsInstance(result, str)
        self.assertTrue(result)
        
        match = resolve(result)
        self.assertEqual(match.url_name, 'celery-materialization-status')
        
        task = AsyncResult(match.kwargs['id'])
        self.assertIsInstance(task, AsyncResult)
        self.await_result_ready(task)
        
        upload.refresh_from_db()
        actual = upload.file.read()
        self.assertEqual(actual, b'baz')
    
    def test_purge_task_uses_upload_method(self):
        with patch.object(Upload, 'purge') as mocked_method:
            purge()
            mocked_method.assert_called_once_with()

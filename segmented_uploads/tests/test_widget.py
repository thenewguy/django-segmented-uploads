from unittest.mock import patch

from django.core.files.base import ContentFile
from django.db import transaction
from django.forms import Field
from django.test import TestCase, TransactionTestCase

from segmented_uploads.widgets import SegmentedFileInput

from ..models import Upload, UploadSecret, UploadSegment
from .forms import SegmentedFileForm


class WidgetRenderTest(TestCase):
    def test_segmented_file_input(self):
        form = SegmentedFileForm()
        field = form['file']
        self.assertEqual(str(field), '<input type="file" name="file" required id="id_file">')
    
    def test_segmented_file_input_with_initial_value(self):
        form = SegmentedFileForm(initial={'file': ContentFile(b'baz', name='baz.txt')})
        field = form['file']
        self.assertEqual(str(field), '<input type="file" name="file" id="id_file">')


class WidgetValueFromDataDictMixin(object):
    def setUp(self):
        self.upload = upload = Upload.objects.create(token='some-token', session='some-session')
        segment = UploadSegment.objects.create(index=1, file=ContentFile(b'baz', name='baz.txt'), upload=upload)
        secret = UploadSecret.objects.create(upload=upload)
        upload.materialize(force=True)
        self.expected_upload_file_name = upload.file.name
        self.name = 'file'
        self.data = {self.name: secret.value}
        self.files = {}

    def test_value(self):
        self.assertNotIn('file', self.files)
        widget = SegmentedFileInput()
        value = widget.value_from_datadict(self.data, self.files, self.name)
        self.assertEqual(value.read(), b'baz')
        self.assertIn('file', self.files)
        self.assertIs(value, self.files['file'])
    
    def test_idempotence(self):
        widget = SegmentedFileInput()
        value1 = widget.value_from_datadict(self.data, self.files, self.name)
        value2 = widget.value_from_datadict(self.data, self.files, self.name)
        self.assertEqual(value1.read(), b'baz')
        self.assertEqual(value2.read(), b'')
        value2.seek(0)
        self.assertEqual(value2.read(), b'baz')
        self.assertEqual(value1, value2)
        self.assertIs(value1, value2)


class FooException(Exception):
    pass


class WidgetValueFromDataDictTransactionTestCase(WidgetValueFromDataDictMixin, TransactionTestCase):
    def test_cleanup(self):
        '''
        Tests under `segmented_uploads.tests.testapp.tests` using 
        `WidgetTests._test_upload()` demonstrate that cleanup works as expected via
        forms. This test is intended to ensure we cleanup gracefully when unhandled
        exceptions are encountered.
        '''
        widget = SegmentedFileInput()
        with patch.object(Upload, 'delete') as mocked_method:
            mocked_method.side_effect = FooException
            value = widget.value_from_datadict(self.data, self.files, self.name)
        self.assertTrue(Upload.objects.filter(pk=self.upload.pk).exists())
        self.upload.refresh_from_db()
        self.assertTrue(self.upload.file.storage.exists(self.upload.file.name))
        self.assertEqual(self.expected_upload_file_name, self.upload.file.name)
        self.assertTrue(self.upload.lingering)

from django.core.exceptions import SuspiciousOperation
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile, SimpleUploadedFile
from django.test import TestCase, TransactionTestCase

from ..models import BoundUploadedFile, Upload, UploadSecret, UploadSegment
from .forms import SegmentedFileForm


class FormTests(TestCase):
    def setUp(self):
        upload = Upload.objects.create(token='some-token', session='some-session')
        segment = UploadSegment.objects.create(index=1, file=ContentFile(b'baz', name='baz.txt'), upload=upload)
        secret = UploadSecret.objects.create(upload=upload)
        upload.materialize(force=True)
        self.form = SegmentedFileForm({'file': secret.value}, {})
        self.bad_form = SegmentedFileForm({'file': 'does-not-exist'}, {})
        self.fallback_form = SegmentedFileForm({}, {'file': SimpleUploadedFile('foo.txt', b'foo')})
        
    def test_form_is_valid(self):
        self.assertTrue(self.form.is_valid())
    
    def test_bad_form_is_valid(self):
        with self.assertRaises(SuspiciousOperation):
            self.bad_form.is_valid()
    
    def test_fallback_form_is_valid(self):
        self.assertTrue(self.fallback_form.is_valid())
    
    def test_form_file_value(self):
        self.assertTrue(self.form.is_valid())
        f = self.form.cleaned_data['file']
        self.assertIsInstance(f, UploadedFile)
        self.assertIsInstance(f, BoundUploadedFile)
        self.assertEqual(f.read(), b'baz')
    
    def test_fallback_form_file_value(self):
        self.assertTrue(self.fallback_form.is_valid())
        f = self.fallback_form.cleaned_data['file']
        self.assertIsInstance(f, UploadedFile)
        self.assertNotIsInstance(f, BoundUploadedFile)
        self.assertEqual(f.read(), b'foo')
    
    def test_form_file_changed(self):
        self.assertTrue(self.form.is_valid())
        self.assertIn('file', self.form.changed_data)
    
    def test_bad_form_file_changed(self):
        with self.assertRaises(SuspiciousOperation):
            self.assertIn('file', self.bad_form.changed_data)
    
    def test_fallback_form_file_changed(self):
        self.assertTrue(self.fallback_form.is_valid())
        self.assertIn('file', self.fallback_form.changed_data)


class AutocommitFormTests(TransactionTestCase):
    def setUp(self):
        upload = Upload.objects.create(token='some-token', session='some-session')
        segment = UploadSegment.objects.create(index=1, file=ContentFile(b'baz', name='baz.txt'), upload=upload)
        secret = UploadSecret.objects.create(upload=upload)
        upload.materialize(force=True)
        self.form = SegmentedFileForm({'file': secret.value}, {})
    
    def test_is_valid_and_has_changed(self):
        self.assertTrue(self.form.is_valid())
        self.assertTrue(self.form.has_changed())

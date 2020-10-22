from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.test import TestCase

from ..models import Upload, UploadSecret


class UploadSecretTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.upload = Upload.objects.create(token='some-token', session='some-session')
        cls.secret = UploadSecret.objects.create(upload=cls.upload)
    
    def test_create(self):
        secret = UploadSecret()
        secret.upload = self.upload
        secret.full_clean()
        secret.save()
    
    def test_protects_upload_delete(self):
        with self.assertRaises(models.ProtectedError):
            self.upload.delete()
    
    def test_reverse_relation(self):
        self.assertEqual(self.upload.secrets.first(), self.secret)
    
    @patch('secrets.token_urlsafe', return_value='not-so-secret')
    def test_value(self, mock_method):
        secret = UploadSecret.objects.create(upload=self.upload)
        mock_method.assert_called_once_with(191)
        self.assertEqual(secret.value, 'not-so-secret')
        self.assertEqual(secret.pk, 'not-so-secret')
        self.assertEqual(len(self.secret.value), 255)

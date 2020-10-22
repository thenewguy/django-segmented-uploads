from io import BytesIO
from os.path import basename
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import models
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes

from ..models import Upload, UploadSegment


class BaseUploadViewTests(TestCase):
    endpoint = reverse('segmented-upload-endpoint')
    
    def setUp(self):
        super().setUp()
        
        self.user = get_user_model().objects.create_user('some-user', 'some-user@example.com', 'Some User')
        self.identifier = 'some-token'
        self.segment_data = b'some content we will check hash against'
        

class CommonTestsMixin(object):
    def get_upload(self, identifier):
        raise NotImplementedError
    
    def test_get_segment_missing(self):
        response = self.client.get(self.endpoint, {'identifier': 'unknown', 'index': 1})
        self.assertEqual(response.status_code, 204)
    
    def test_get_segment_exists(self):
        response = self.client.get(self.endpoint, {'identifier': self.identifier, 'index': 1})
        self.assertEqual(response.status_code, 200)
    
    def test_get_segment_exists_digest_mismatch(self):
        response = self.client.get(self.endpoint, {'identifier': self.identifier, 'index': 1, 'digest': 'no-match'})
        self.assertEqual(response.status_code, 204)
    
    def test_get_segment_exists_missing_file(self):
        self.segment.file.delete()
        self.segment.refresh_from_db(fields=['file'])
        self.assertFalse(self.segment.file)
        response = self.client.get(self.endpoint, {'identifier': self.identifier, 'index': 1})
        self.assertEqual(response.status_code, 204)
    
    def test_get_segment_exists_missing_storage_file(self):
        self.segment.file.storage.delete(self.segment.file.name)
        self.segment.refresh_from_db(fields=['file'])
        self.assertTrue(self.segment.file)
        self.assertFalse(self.segment.file.storage.exists(self.segment.file.name))
        response = self.client.get(self.endpoint, {'identifier': self.identifier, 'index': 1})
        self.assertEqual(response.status_code, 204)
    
    def test_get_known_identifier_segment_missing_index(self):
        response = self.client.get(self.endpoint, {'identifier': self.identifier, 'index': 2})
        self.assertEqual(response.status_code, 204)
    
    def test_post_segment(self):
        alt_data = force_bytes('unknown-content-{}'.format(uuid4()))
        response = self.client.post(self.endpoint, {'identifier': 'unknown', 'index': 1, 'file': BytesIO(alt_data), 'filename': 'unknown.txt'})
        self.assertEqual(response.status_code, 200)
        
        alt_upload = self.get_upload('unknown')
        segment = alt_upload.segments.first()
        self.assertTrue(segment)
        self.assertEqual(segment.index, 1)
        self.assertEqual(segment.file.read(), alt_data)
        
        expected_file_name = '{upload}-{segment}-{index}-{attempt}-{filename}'.format(
            upload=segment.upload.pk,
            segment=segment.pk,
            index=1,
            attempt=1,
            filename='unknown.txt',
        )
        first_file_name = segment.file.name
        self.assertEqual(basename(first_file_name), expected_file_name)
        
        self.assertNotEqual(self.upload.segments.last().index, 2)
        other_data = force_bytes('some-content-{}'.format(uuid4()))
        response = self.client.post(self.endpoint, {'identifier': self.identifier, 'index': 2, 'file': BytesIO(other_data)})
        self.assertEqual(response.status_code, 200)
        
        self.assertNotEqual(alt_upload.pk, self.upload.pk)
        
        segment = self.upload.segments.last()
        self.assertTrue(segment)
        self.assertEqual(segment.index, 2)
        self.assertEqual(segment.file.read(), other_data)
    
    def test_post_segment_missing_file_on_storage(self):
        self.segment.file.storage.delete(self.segment.file.name)
        self.segment.refresh_from_db(fields=['file'])
        self.assertTrue(self.segment.file)
        self.assertFalse(self.segment.file.storage.exists(self.segment.file.name))
        
        alt_data = force_bytes('unknown-content-{}'.format(uuid4()))
        response = self.client.post(self.endpoint, {'identifier': self.identifier, 'index': 1, 'file': BytesIO(alt_data), 'filename': 'unknown.txt'})
        self.assertEqual(response.status_code, 200)
        
        self.segment.refresh_from_db(fields=['file'])
        self.assertEqual(self.segment.file.read(), alt_data)
    
    def test_post_with_digest_segment_missing_file_on_storage(self):
        for algo, digest in (
            # expected is the algorithm's hexdigest for an empty string
            ('', ''),
            ('md5', 'f26c2f431a8f57ae8013881556f8e279'),
            ('sha1', '0b3d8b29493059afd7f9912106279c4643ac4939'),
        ):
            with self.subTest(algo=algo):
                self.segment.file = str(uuid4()) # generate a random filename that doesn't exist
                self.segment.save()
                self.segment.refresh_from_db(fields=['file'])
                self.assertTrue(self.segment.file)
                self.assertFalse(self.segment.file.storage.exists(self.segment.file.name))
                
                alt_data = force_bytes('def456')
                response = self.client.post(self.endpoint, {'identifier': self.identifier, 'index': 1, 'file': BytesIO(alt_data), 'filename': 'def456.txt', 'algorithm': algo, 'digest': digest})
                self.assertEqual(response.status_code, 200)
                
                self.segment.refresh_from_db(fields=['file'])
                self.assertEqual(self.segment.file.read(), alt_data)
    
    def test_duplicate_segment_post_overrides_file(self):
        alt_data = force_bytes('unknown-content-{}'.format(uuid4()))
        alt_file = BytesIO(alt_data)
        post_data = {'identifier': 'unknown', 'index': 1, 'file': alt_file}
        response = self.client.post(self.endpoint, post_data)
        self.assertEqual(response.status_code, 200)
        
        alt_upload = self.get_upload('unknown')
        segment = alt_upload.segments.first()
        self.assertTrue(segment)
        self.assertEqual(segment.index, 1)
        self.assertEqual(segment.file.read(), alt_data)
        
        expected_file_name = '{upload}-{segment}-{index}-{attempt}-{filename}'.format(
            upload=segment.upload.pk,
            segment=segment.pk,
            index=1,
            attempt=1,
            filename='',
        )
        first_file_name = segment.file.name
        self.assertEqual(basename(first_file_name), expected_file_name)
        
        alt_file.seek(0)
        response = self.client.post(self.endpoint, post_data)
        self.assertEqual(response.status_code, 200)
        
        segment.refresh_from_db()
        self.assertEqual(segment.file.read(), alt_data)
        self.assertNotEqual(segment.file.name, first_file_name)
    
    def test_duplicate_segment_post_with_digest_keeps_file(self):
        alt_data = force_bytes('abc123')
        alt_file = BytesIO(alt_data)
        post_data = {'identifier': 'abc', 'index': 1, 'file': alt_file, 'digest': 'e99a18c428cb38d5f260853678922e03', 'algorithm': 'md5'}
        
        actual_digest = Upload.hexdigest(alt_file.read(), algorithm=post_data['algorithm'])
        self.assertEqual(post_data['digest'], actual_digest)
        
        alt_file.seek(0)
        response = self.client.post(self.endpoint, post_data)
        self.assertEqual(response.status_code, 200)
        
        alt_upload = self.get_upload('abc')
        segment = alt_upload.segments.first()
        self.assertTrue(segment)
        self.assertEqual(segment.index, 1)
        self.assertEqual(segment.file.read(), alt_data)
        
        expected_file_name = '{upload}-{segment}-{index}-{attempt}-{filename}'.format(
            upload=segment.upload.pk,
            segment=segment.pk,
            index=1,
            attempt=1,
            filename='',
        )
        first_file_name = segment.file.name
        self.assertEqual(basename(first_file_name), expected_file_name)
        
        alt_file.seek(0)
        response = self.client.post(self.endpoint, post_data)
        self.assertEqual(response.status_code, 200)
        
        segment.refresh_from_db()
        self.assertEqual(segment.file.read(), alt_data)
        self.assertEqual(segment.file.name, first_file_name)
    
    def test_materialize(self):
        self.assertFalse(self.upload.file)
        
        for algo in ('', 'md5', 'sha1'):
            with self.subTest(algorithm=algo):
                with patch.object(Upload, 'materialize') as mocked_method:
                    response = self.client.post(self.endpoint, {'identifier': self.identifier, 'algorithm': algo})
                    self.assertEqual(response.status_code, 200)
                    mocked_method.assert_called_once_with(algorithm=algo)
    
    @patch('secrets.token_urlsafe', return_value='super-secret')
    def test_secret(self, mocked):
        self.assertFalse(self.upload.file)
        self.upload.file.save('foo', ContentFile('bar'), False)
        self.upload.digest = 'fake-digest'
        self.upload.save()
        self.upload.refresh_from_db()
        self.assertTrue(self.upload.file)
        
        self.assertIsNone(self.upload.secrets.filter().first())
        response = self.client.post(self.endpoint, {'identifier': self.identifier, 'digest': 'fake-digest'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'super-secret')
        
        secret = self.upload.secrets.filter().first()
        self.assertIsNotNone(secret)
        self.assertEqual(secret.value, 'super-secret')


class UserUploadViewTests(CommonTestsMixin, BaseUploadViewTests):
    def setUp(self):
        super().setUp()
        
        self.upload = Upload.objects.create(token=Upload.hexdigest(self.identifier), user=self.user)
        self.segment = UploadSegment.objects.create(index=1, file=ContentFile(self.segment_data, name='segment'), upload=self.upload)
        self.client.force_login(self.user)
    
    def get_upload(self, identifier):
        return Upload.objects.get(token=Upload.hexdigest(identifier), user=self.user)


class SessionUploadViewTests(CommonTestsMixin, BaseUploadViewTests):
    def setUp(self):
        super().setUp()
        
        self.session = self.client.session
        self.session.save()
        
        self.upload = Upload.objects.create(token=Upload.hexdigest(self.identifier), session=self.session.session_key)
        self.segment = UploadSegment.objects.create(index=1, file=ContentFile(self.segment_data, name='segment'), upload=self.upload)
    
    def get_upload(self, identifier):
        return Upload.objects.get(token=Upload.hexdigest(identifier), session=self.session.session_key)

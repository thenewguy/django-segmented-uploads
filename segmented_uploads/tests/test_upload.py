from unittest.mock import patch, ANY as MOCK_ANY

from django.contrib.auth import get_user_model
from django.core.exceptions import SuspiciousOperation, ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from redis.exceptions import LockError as RedisLockError

from ..models import BoundUploadedFile, Upload, UploadSegment
from ..signals import trigger_materialization
from ..utils import cache_redis


class SimpleUploadTests(SimpleTestCase):
    def test_db_index_fields(self):
        for name in ('token', 'user', 'session'):
            with self.subTest(name=name):
                field = Upload._meta.get_field(name)
                self.assertTrue(field.db_index)


class UploadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('some-user', 'some-user@example.com', 'Some User')
        cls.upload_for_session = Upload.objects.create(token='session-token-value', session='session-value')
        cls.upload_for_user = Upload.objects.create(token='user-token-value', user=cls.user)
    
    def tearDown(self):
        if self.upload_for_session.file:
            self.upload_for_session.file.delete()
        
        if self.upload_for_user.file:
            self.upload_for_user.file.delete()
    
    def test_upload_for_session_user_is_none(self):
        self.assertIsNone(self.upload_for_session.user)
    
    def test_upload_for_user_session_is_none(self):
        self.assertIsNone(self.upload_for_user.session)
    
    @override_settings(UPLOADS_LINGER_DAYS=0)
    def test_upload_purges_expired(self):
        self.assertEqual(Upload.objects.count(), 2)
        count = Upload.purge()[0]
        self.assertEqual(count, 2)
        self.assertEqual(Upload.objects.count(), 0)
    
    def test_upload_only_purges_expired(self):
        self.assertEqual(Upload.objects.count(), 2)
        count = Upload.purge()[0]
        self.assertEqual(count, 0)
        self.assertEqual(Upload.objects.count(), 2)
    
    def test_upload_purges_lingering(self):
        self.assertEqual(Upload.objects.count(), 2)
        self.upload_for_session.lingering = True
        self.upload_for_session.save()
        count = Upload.purge()[0]
        self.assertEqual(count, 1)
        self.assertEqual(Upload.objects.count(), 1)
    
    def test_create_for_session(self):
        upload = Upload()
        upload.token = 'some-token'
        upload.session = 'some-session'
        upload.full_clean()
        upload.save()
    
    def test_create_for_user(self):
        upload = Upload()
        upload.token = 'some-token'
        upload.user = self.user
        upload.full_clean()
        upload.save()
    
    def test_cannot_create_for_session_with_empty_string(self):
        upload = Upload()
        upload.token = 'some-token'
        upload.session = ''
        with self.assertRaises(ValidationError):
            upload.full_clean()
    
    def test_cannot_create_with_session_and_user(self):
        upload = Upload()
        upload.token = 'some-token'
        upload.user = self.user
        upload.session = 'some-session'
        with self.assertRaises(ValidationError):
            upload.full_clean()
    
    def test_cannot_create_without_session_or_user(self):
        upload = Upload()
        upload.token = 'some-token'
        with self.assertRaises(ValidationError):
            upload.full_clean()
    
    def test_cannot_duplicate_for_user(self):
        with self.assertRaises(IntegrityError):
            Upload.objects.create(token='user-token-value', user=self.user)
    
    def test_cannot_duplicate_for_session(self):
        with self.assertRaises(IntegrityError):
            Upload.objects.create(token='session-token-value', session='session-value')
    
    def test_duplicate_materialize_is_suspicious(self):
        self.upload_for_session.materialize()
        with self.assertRaises(SuspiciousOperation):
            self.upload_for_session.materialize()
    
    def test_materialize_lock_key(self):
        pk = self.upload_for_session.pk
        expected = f'segmented_uploads;Upload;{pk};materialize'
        self.assertEqual(self.upload_for_session.materialize_lock_key, expected)
        self.assertNotEqual(
            self.upload_for_session.materialize_lock_key,
            self.upload_for_user.materialize_lock_key,
        )
    
    def test_forced_materialize_is_locked(self):
        with cache_redis.lock(self.upload_for_session.materialize_lock_key, timeout=60, blocking_timeout=-1) as lock:
            with self.assertRaises(RedisLockError):
                self.upload_for_session.materialize(force=True)
    
    def test_trigger_lock_key(self):
        pk = self.upload_for_session.pk
        expected = f'segmented_uploads;Upload;{pk};trigger'
        self.assertEqual(self.upload_for_session.trigger_lock_key, expected)
        self.assertNotEqual(
            self.upload_for_session.trigger_lock_key,
            self.upload_for_user.trigger_lock_key,
        )
    
    def test_trigger_is_locked(self):
        with cache_redis.lock(self.upload_for_session.trigger_lock_key, timeout=5, blocking_timeout=-1) as lock:
            with self.assertRaises(RedisLockError):
                self.upload_for_session.trigger(algorithm='')
    
    def test_materialize_calls_trigger(self):
        for algo in ('', 'md5', 'sha1'):
            with self.subTest(algorithm=algo):
                with patch.object(Upload, 'trigger') as mocked_method:
                    # pre-lock here to confirm no materialization occurs
                    with cache_redis.lock(self.upload_for_session.materialize_lock_key, timeout=60, blocking_timeout=-1) as lock:
                        self.upload_for_session.materialize(algorithm=algo)
                    mocked_method.assert_called_once_with(algo)
    
    def test_trigger_sends_signal(self):
        with patch.object(trigger_materialization, 'send') as mocked_method:
            self.upload_for_session.trigger(algorithm='foo')
            mocked_method.assert_called_once_with(
                sender=self.upload_for_session.__class__,
                instance=self.upload_for_session,
                algorithm='foo',
                lock=MOCK_ANY,
            )
    
    def test_bound_uploaded_file(self):
        with self.assertRaises(ValueError):
            BoundUploadedFile(self.upload_for_session)
        
        upload = Upload.objects.create(token='the-right-name', session='bar')
        UploadSegment.objects.create(index=1, file=ContentFile('baz', name='the-wrong-name.txt'), upload=upload)
        upload.materialize()
        f = BoundUploadedFile(upload)
        self.assertIsInstance(f, BoundUploadedFile)
        self.assertEqual(f.name, 'the-right-name')
        self.assertEqual(f.content_type, 'application/octet-stream')
        self.assertEqual(f.size, 3)
        self.assertEqual(f.read(), b'baz')
        
        upload.filename = 'the-updated-name.pdf'
        f2 = BoundUploadedFile(upload)
        
        # verify upload.filename is preferred
        self.assertEqual(f2.name, 'the-updated-name.pdf')
    
    def test_unmaterialized_upload_uploaded_file(self):
        with self.assertRaises(ValueError):
            self.upload_for_session.uploaded_file
    
    def test_materialized_upload_uploaded_file_is_bound_once(self):
        upload = Upload.objects.create(token='foo', session='bar')
        UploadSegment.objects.create(index=1, file=ContentFile('baz', name='an-awesome-name.txt'), upload=upload)
        upload.materialize()
        with patch.object(BoundUploadedFile, '__init__') as mocked_method_1:
            mocked_method_1.return_value = None
            upload.uploaded_file
            mocked_method_1.assert_called_once_with(upload)
        
        with patch.object(BoundUploadedFile, '__init__') as mocked_method_2:
            mocked_method_2.return_value = None
            upload.uploaded_file
            mocked_method_2.assert_not_called()
    
    def test_uploaded_file_type(self):
        upload = Upload.objects.create(token='foo', session='bar')
        UploadSegment.objects.create(index=1, file=ContentFile('baz', name='an-awesome-name.txt'), upload=upload)
        upload.materialize()
        self.assertIsInstance(upload.uploaded_file, BoundUploadedFile)
    
    def test_materialized_upload_uploaded_file_is_bound_the_same(self):
        upload = Upload.objects.create(token='foo', session='bar')
        UploadSegment.objects.create(index=1, file=ContentFile('baz', name='an-awesome-name.txt'), upload=upload)
        upload.materialize()
        f1 = upload.uploaded_file
        self.assertEqual(f1.name, 'foo')
        
        # verify file name doesn't update automatically
        upload.filename = 'the-updated-name.pdf'
        f2 = upload.uploaded_file
        self.assertEqual(f2.name, 'foo')
        self.assertIs(f1, f2)
        
        # verify file name will change if the property is reset
        upload._uploaded_file = None
        f3 = upload.uploaded_file
        self.assertEqual(f3.name, 'the-updated-name.pdf')
        self.assertNotEqual(f3.name, f1.name)
        self.assertIsNot(f3, f1)
        
    def test_materialized_file_content(self):
        for algo, expected in (
            ('', ''),
            ('md5', '55b84a9d317184fe61224bfb4a060fb0'),
            ('sha1', 'b85e2d4914e22b5ad3b82b312b3dc405dc17dcb8'),
        ):
            with self.subTest(algorithm=algo):
                upload = Upload.objects.create(token='token-{}-{}'.format(algo, expected), session='session-{}-{}'.format(algo, expected))
                UploadSegment.objects.create(index=1, file=ContentFile('1,', name='1'), upload=upload)
                UploadSegment.objects.create(index=3, file=ContentFile('3', name='3'), upload=upload)
                UploadSegment.objects.create(index=2, file=ContentFile('2,', name='2'), upload=upload)
                upload.materialize(algorithm=algo)
                self.assertEqual(upload.file.read(), b'1,2,3')
                self.assertEqual(upload.digest, expected)
    
    def test_uploaded_file_content(self):
        upload = Upload.objects.create(token='some-token', session='some-session')
        UploadSegment.objects.create(index=1, file=ContentFile('one,', name='1'), upload=upload)
        UploadSegment.objects.create(index=3, file=ContentFile('three', name='3'), upload=upload)
        UploadSegment.objects.create(index=2, file=ContentFile('two,', name='2'), upload=upload)
        upload.materialize()
        self.assertEqual(upload.uploaded_file.read(), b'one,two,three')
    
    def test_digest_algorithms(self):
        for algo, expected in (
            # expected is the algorithm's hexdigest for an empty string
            ('', ''),
            ('md5', 'd41d8cd98f00b204e9800998ecf8427e'),
            ('sha1', 'da39a3ee5e6b4b0d3255bfef95601890afd80709'),
        ):
            with self.subTest(algorithm=algo):
                upload = Upload.objects.create(token=algo, session=algo)
                upload.materialize(algorithm=algo)
                self.assertEqual(upload.digest, expected)


class UploadTransactionTests(TransactionTestCase):
    def test_delete_removes_file(self):
        data = b'upload-69b66b68-743e-4c26-b3d8-6b4432ce7173'
        upload = Upload.objects.create(
            token='some-token',
            session='some-session',
            file=ContentFile(data, name='upload-file'),
        )
        
        name = upload.file.name
        storage = upload.file.storage
        
        self.assertTrue(storage.exists(name))
        self.assertEqual(storage.open(name).read(), data)
        
        with transaction.atomic():
            upload.delete()
            self.assertTrue(
                storage.exists(name),
                'file should not be removed before the transaction is committed')
        self.assertFalse(storage.exists(name))

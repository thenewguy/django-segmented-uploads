from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase, TransactionTestCase

from ..models import Upload, UploadSegment


class UploadSegmentTests(TestCase):
    def setUp(self):
        self.upload = Upload.objects.create(token='some-token', session='some-session')
        self.segment = UploadSegment.objects.create(index=1, file=ContentFile('some content', name='segment'), upload=self.upload)
            
    def test_create(self):
        segment = UploadSegment()
        segment.upload = self.upload
        segment.index = 2
        segment.file = ContentFile('data', name='foo')
        segment.full_clean()
        segment.save()
    
    def test_get_digest(self):
        for algo, expected in (
            # expected is the algorithm's hexdigest for an empty string
            ('', ''),
            ('md5', '9893532233caff98cd083a116b013c0b'),
            ('sha1', '94e66df8cd09d410c62d9e0dc59d3a884e458e05'),
        ):
            with self.subTest(algorithm=algo):
                self.assertEqual(self.segment.get_digest(algorithm=algo), expected)
    
    def test_get_digest_missing_file_on_storage(self):
        self.assertTrue(self.segment.file)
        self.assertTrue(self.segment.file.name)
        self.segment.file.storage.delete(self.segment.file.name)
        self.segment.refresh_from_db(fields=['file'])
        self.assertTrue(self.segment.file)
        self.assertFalse(self.segment.file.storage.exists(self.segment.file.name))
        
        with self.assertRaises(FileNotFoundError):
            self.segment.get_digest()
    
    def test_get_digest_missing_file(self):
        self.segment.file.delete()
        self.segment.refresh_from_db(fields=['file'])
        self.assertFalse(self.segment.file)
        
        with self.assertRaises(FileNotFoundError):
            self.segment.get_digest()


class UploadSegmentTransactionTests(TransactionTestCase):
    def test_delete_removes_file(self):
        data = b'segment-69b66b68-743e-4c26-b3d8-6b4432ce7173'
        segment = UploadSegment.objects.create(
            index=1,
            file=ContentFile(data, name='segment'),
            upload=Upload.objects.create(token='some-token', session='some-session'),
        )
        
        name = segment.file.name
        storage = segment.file.storage
        
        self.assertTrue(storage.exists(name))
        self.assertEqual(storage.open(name).read(), data)
        
        with transaction.atomic():
            segment.delete()
            self.assertTrue(
                storage.exists(name),
                'file should not be removed before the transaction is committed')
        self.assertFalse(storage.exists(name))

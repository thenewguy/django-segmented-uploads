from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TransactionTestCase, TestCase
from django.urls import reverse

from segmented_uploads.models import Upload, UploadSecret, UploadSegment
from segmented_uploads.tests.utils import EmptyStorageMixin

from .models import Author


class MethodMixin(object):
    def _test_upload(self, file_upload, file_content, photo_upload, photo_content, **kwargs):
        self.assertFalse(Author.objects.filter(name='fancy friend').exists())
        with transaction.atomic():
            response = self.client.post(reverse('author-create'), {
                'name': 'fancy friend',
                'file': UploadSecret.objects.create(upload=file_upload).value,
                'photo': UploadSecret.objects.create(upload=photo_upload).value,
            })
            self.assertTrue(Upload.objects.filter(pk=file_upload.pk).exists())
            self.assertTrue(file_upload.file.storage.exists(file_upload.file.name))
            self.assertTrue(Upload.objects.filter(pk=photo_upload.pk).exists())
            self.assertTrue(photo_upload.file.storage.exists(photo_upload.file.name))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Author.objects.filter(name='fancy friend').count(), 1)
        self.assertEqual(Author.objects.filter(name='fancy friend').first().file.read(), file_content)
        self.assertEqual(Author.objects.filter(name='fancy friend').first().photo.read(), photo_content)
        self.assertFalse(Upload.objects.filter(pk=file_upload.pk).exists())
        self.assertFalse(file_upload.file.storage.exists(file_upload.file.name))
        self.assertFalse(Upload.objects.filter(pk=photo_upload.pk).exists())
        self.assertFalse(photo_upload.file.storage.exists(photo_upload.file.name))
        
    def _get_single_upload(self, **kwargs):
        content = b'!'
        upload = Upload.objects.create(token='a', **kwargs)
        UploadSegment.objects.create(index=1, file=ContentFile(content, name='1'), upload=upload)
        upload.materialize()
        return upload, content
    
    def _get_two_uploads(self, **kwargs):
        content_1 = b'$'
        upload_1 = Upload.objects.create(token='1', **kwargs)
        UploadSegment.objects.create(index=1, file=ContentFile(content_1, name='1'), upload=upload_1)
        upload_1.materialize()
        
        content_2 = b'^'
        upload_2 = Upload.objects.create(token='2', **kwargs)
        UploadSegment.objects.create(index=1, file=ContentFile(content_2, name='2'), upload=upload_2)
        upload_2.materialize()
        
        return upload_1, content_1, upload_2, content_2


class WidgetTests(MethodMixin, TransactionTestCase):
    def test_fallback(self):
        self.assertFalse(Author.objects.filter(name='boring boy').exists())
        response = self.client.post(reverse('author-create'), {
            'name': 'boring boy',
            'file': SimpleUploadedFile("file.txt", b"some content", content_type="text/plain"),
            'photo': SimpleUploadedFile("photo.txt", b"different content", content_type="text/plain"),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Author.objects.filter(name='boring boy').count(), 1)
        self.assertEqual(Author.objects.filter(name='boring boy').first().file.read(), b"some content")
        self.assertEqual(Author.objects.filter(name='boring boy').first().photo.read(), b"different content")
    
    def test_single_upload_for_session(self):
        session = self.client.session
        session.save()
        opts = dict(session=session.session_key)
        upload, content = self._get_single_upload(**opts)
        self._test_upload(upload, content, upload, content, **opts)
    
    def test_double_upload_for_session(self):
        session = self.client.session
        session.save()
        opts = dict(session=session.session_key)
        upload1, content1, upload2, content2 = self._get_two_uploads(**opts)
        self._test_upload(upload1, content1, upload2, content2, **opts)
    
    def test_single_upload_for_user(self):
        user = get_user_model().objects.create_user('some-user', 'some-user@example.com', 'Some User')
        opts = dict(user=user)
        upload, content = self._get_single_upload(**opts)
        self.client.force_login(user)
        self._test_upload(upload, content, upload, content, **opts)
    
    def test_double_upload_for_user(self):
        user = get_user_model().objects.create_user('some-user', 'some-user@example.com', 'Some User')
        opts = dict(user=user)
        upload1, content1, upload2, content2 = self._get_two_uploads(**opts)
        self.client.force_login(user)
        self._test_upload(upload1, content1, upload2, content2, **opts)


class CleanupTests(EmptyStorageMixin, MethodMixin, TransactionTestCase):
    def get_author_file_names(self):
        files = []
        for author in Author.objects.all():
            files.extend(author.file.name)
            files.extend(author.photo.name)
        return files
    
    def test_file_assignment_moves_after_upload(self):
        session = self.client.session
        session.save()
        opts = dict(session=session.session_key)
        upload1, content1, upload2, content2 = self._get_two_uploads(**opts)
        self._test_upload(upload1, content1, upload2, content2, **opts)
        author_file_names = self.get_author_file_names()
        self.assertNotIn(upload1.file.name, author_file_names)
        self.assertNotIn(upload2.file.name, author_file_names)
    
    def test_cleanup_removes_stored_files_for_session(self):
        storage = Upload._meta.get_field('file').storage
        self.ensure_empty_storage(storage)
        session = self.client.session
        session.save()
        opts = dict(session=session.session_key)
        upload1, content1, upload2, content2 = self._get_two_uploads(**opts)
        self._test_upload(upload1, content1, upload2, content2, **opts)
        author_file_names = self.get_author_file_names()
        self.assertEmptyStorage(storage, allow_empty_dirs=True, allowed_file_names=author_file_names)

    def test_cleanup_removes_stored_files_for_user(self):
        storage = Upload._meta.get_field('file').storage
        self.ensure_empty_storage(storage)
        user = get_user_model().objects.create_user('some-user', 'some-user@example.com', 'Some User')
        opts = dict(user=user)
        upload1, content1, upload2, content2 = self._get_two_uploads(**opts)
        self.client.force_login(user)
        self._test_upload(upload1, content1, upload2, content2, **opts)
        author_file_names = self.get_author_file_names()
        self.assertEmptyStorage(storage, allow_empty_dirs=True, allowed_file_names=author_file_names)

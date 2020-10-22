import secrets
import uuid
from datetime import timedelta
from hashlib import md5, sha1
from tempfile import TemporaryFile, gettempdir

from django.conf import settings
from django.core.exceptions import SuspiciousOperation, ValidationError
from django.core.files import File
from django.core.files.uploadedfile import TemporaryUploadedFile
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch.dispatcher import receiver
from django.utils import timezone
from django.utils.encoding import force_bytes

from .signals import trigger_materialization
from .utils import cache_redis
from .validators import validate_truthy_or_null


TEMP_DIR = settings.FILE_UPLOAD_TEMP_DIR or gettempdir()
noop = lambda *args, **kwargs: None
noop_str = lambda *args, **kwargs: ''


class NoopHasher(object):
    update = noop
    hexdigest = noop_str
    
    def __call__(self, *args, **kwargs):
        return self


noop_hasher = NoopHasher()

hasher_map = {
    'md5': md5,
    'sha1': sha1,
}


def get_hasher(algorithm, data=''):
    return hasher_map.get(algorithm, noop_hasher)(force_bytes(data))


def instance_upload_to(instance, filename):
    return instance.get_file_upload_to(filename)


class UploadToMixin(object):
    upload_to_prefix = ''
    
    def get_file_upload_to(self, filename):
        pieces = [self.upload_to_prefix] + str(uuid.uuid4()).split('-') + [filename]
        return "/".join([s for s in [p.strip('/').strip() for p in pieces] if s])

UploadToMixin.upload_to = instance_upload_to


def set_error_for_field(errors, fields, error):
    for field in fields:
        errors.setdefault(field, []).append(error)


class BoundUploadedFile(TemporaryUploadedFile):
    def __init__(self, upload):
        if not upload.file:
            raise ValueError('not materialized')
        super().__init__(
            name=upload.filename or upload.token,
            content_type='application/octet-stream',
            size=upload.file.size,
            charset=None,
        )
        self.upload = upload
        with upload.file.storage.open(upload.file.name) as f:
            for chunk in f.chunks():
                self.file.write(chunk)
        self.file.seek(0)


class Upload(UploadToMixin, models.Model):
    upload_to_prefix = 'uploads/'
    
    class Meta:
        unique_together = [
            ["token", "session"],
            ["token", "user"],
        ]

    token = models.CharField(max_length=255, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, default=None, editable=False)
    session = models.CharField(max_length=255, db_index=True, null=True, default=None, editable=False)
    filename = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to=UploadToMixin.upload_to, blank=True, editable=False)
    digest = models.CharField(max_length=40, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    lingering = models.BooleanField(default=False)
    
    @property
    def uploaded_file(self):
        if self._uploaded_file is None:
            self._uploaded_file = BoundUploadedFile(self)
        return self._uploaded_file
    _uploaded_file = None
    
    def clean(self):
        errors = {}
        if self.session is None:
            if self.user is None:
                set_error_for_field(errors, ['session', 'user'], 'One of user or session must be set.')
        elif self.user is not None:
            set_error_for_field(errors, ['session', 'user'], 'Only one of user or session may be set.')
        try:
            validate_truthy_or_null(self.session)
        except ValidationError as error:
            set_error_for_field(errors, ['session'], error)
        if errors:
            raise ValidationError(errors)

    @classmethod
    def hexdigest(cls, data='', algorithm='sha1'):
        return get_hasher(algorithm, data=data).hexdigest()
    
    @classmethod
    def purge(cls):
        days = getattr(settings, 'UPLOADS_LINGER_DAYS', 7)
        qs_expired = cls.objects.filter(created_at__lt=timezone.now() - timedelta(days=days))
        qs_lingering = cls.objects.filter(lingering=True)
        qs = qs_lingering | qs_expired
        return qs.delete()
    
    @property
    def materialize_lock_key(self):
        return ';'.join(['segmented_uploads', 'Upload', str(self.pk), 'materialize'])

    @transaction.atomic
    def materialize(self, force=False, algorithm='', **kwargs):
        if self.file:
            raise SuspiciousOperation('already materialized')
        
        if force:
            
            with cache_redis.lock(self.materialize_lock_key, timeout=60, blocking_timeout=-1) as lock:
                
                progress_callback = kwargs.get("progress_callback", noop)
                
                with TemporaryFile(dir=TEMP_DIR) as fp:
                    segments = self.segments.all()
                    segments_len = len(segments)
                    step_count = segments_len + 1
                    hasher = get_hasher(algorithm)
        
                    for i, segment in enumerate(segments, start=1):
                        with segment.file.open() as f:
                            for chunk in f.chunks():
                                fp.write(chunk)
                                hasher.update(chunk)
                        segment.delete()
                        progress_callback(i, step_count)
                        lock.reacquire()
                        
        
                    fp.seek(0)
                    self.digest = hasher.hexdigest()
                    lock.extend(300)
                    self.file.save('{}-{}'.format(self.pk, uuid.uuid4()), File(fp))
                
                progress_callback(step_count, step_count)
        
        else:
            return self.trigger(algorithm)
    
    @property
    def trigger_lock_key(self):
        return ';'.join(['segmented_uploads', 'Upload', str(self.pk), 'trigger'])
    
    def trigger(self, algorithm):
        with cache_redis.lock(self.trigger_lock_key, timeout=5, blocking_timeout=-1) as lock:
            return trigger_materialization.send(sender=self.__class__, instance=self, algorithm=algorithm, lock=lock)


if getattr(settings, 'UPLOADS_MATERIALIZE_SYNCHRONOUSLY', True):
    @receiver(trigger_materialization, sender=Upload)
    def materialize_upload(sender, instance, lock=None, **kwargs):
        instance.materialize(force=True, **kwargs)


def generate_secret_value():
    return secrets.token_urlsafe(191)


class UploadSecret(models.Model):
    upload = models.ForeignKey(Upload, related_name="secrets", on_delete=models.PROTECT)
    value = models.CharField(
        max_length=255,
        primary_key=True,
        default=generate_secret_value,
        editable=False,
    )


class UploadSegment(UploadToMixin, models.Model):
    upload_to_prefix = 'upload-segments/'
    
    class Meta:
        ordering = ["index"]
        unique_together = ("index", "upload")

    file = models.FileField(upload_to=UploadToMixin.upload_to)
    index = models.IntegerField(db_index=True)
    upload = models.ForeignKey(Upload, related_name="segments", on_delete=models.CASCADE)
    attempt_count = models.IntegerField(default=0)
    
    def get_digest(self, **kwargs):
        if not self.file:
            raise FileNotFoundError
        # Individual segments are size limited, so it is acceptable to read them
        # into memory.  The default limit is 10MB.
        with self.file.open() as f:
            data = self.file.read()
        return Upload.hexdigest(data, **kwargs)


@receiver(post_delete, sender=Upload)
@receiver(post_delete, sender=UploadSegment)
def cleanup_file(sender, instance, **kwargs):
    # Pass False so FileField doesn't save the model.
    transaction.on_commit(lambda: instance.file.delete(False))

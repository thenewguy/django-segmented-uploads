import logging
from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousOperation, ValidationError, NON_FIELD_ERRORS
from django.db import models
from django.http import HttpResponse, HttpResponseRedirect, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.generic.base import View
from redis.exceptions import LockError as RedisLockError

from .models import Upload, UploadSecret, UploadSegment, hasher_map

logger = logging.getLogger(__name__)


SEGMENT_LIMIT = getattr(settings, 'UPLOADS_SEGMENT_LIMIT', 100)
SEGMENT_ALLOWABLE_SIZE = getattr(settings, 'UPLOADS_SEGMENT_ALLOWABLE_SIZE', 10485760)


class StateConflictError(Exception):
    pass


def get_param(request, param, default="", required=True, coerce=lambda x: x):
    value = request.POST.get(param, "") or request.GET.get(param, default)
    if not value and required:
        raise SuspiciousOperation("Missing param '%s' is required!" % param)
    if value:
        value = coerce(value)
    return value


def get_user_or_none(request):
    return request.user if request.user.is_authenticated else None


def get_upload_lookups(request):
    identifier = request.POST.get("identifier", "") or request.GET["identifier"]
    kwargs = {
        # we hash the value to make it easy for a client to create unique identifiers
        # e.g. this supports long JSON data if the client so wishes
        'token': Upload.hexdigest(identifier)
    }
    user = kwargs['user'] = get_user_or_none(request)
    if not user:
        session = kwargs['session'] = request.session.session_key
        if not session:
            raise SuspiciousOperation("Session required for anonymous uploads!")
    return kwargs


class UploadView(View):
    def dispatch(self, request, *args, **kwargs):
        try:
            self.validate_user(request=request)
            if request.method != 'PUT':
                self.validate_session(request)
            self.validate_segment_count(request=request)
            self.validate_segment_size(request=request)
            self.validate_total_size(request=request)
            return super().dispatch(request, *args, **kwargs)
        except PermissionDenied as e:
            errors = {NON_FIELD_ERRORS: ['Permission denied: %s.' % e]}
            status = 403
        except SuspiciousOperation as e:
            logger.exception('Suspicious operation encountered while handling upload.')
            errors = {NON_FIELD_ERRORS: [
                'An error (likely out of your control) was encountered while attempting to process this upload: ' + str(e)
            ]}
            status = 500
        except ValidationError as e:
            try:
                errors = e.message_dict
            except AttributeError:
                errors = {NON_FIELD_ERRORS: e.messages}
            status = 400
        except StateConflictError:
            errors = {NON_FIELD_ERRORS: [(
                "Resource state conflict encountered! This is likely a temporary "
                "condition, so try again... but please note that you may need to "
                "wait awhile or seek assistance if the problem persists. Your "
                "current progress should be saved."
            )]}
            status = 409
        return JsonResponse({"errors": errors}, status=status)
            
    
    def options(self, request):
        return JsonResponse({
            "validation": {
                "segment_limit": SEGMENT_LIMIT,
                "segment_allowable_size": SEGMENT_ALLOWABLE_SIZE,
            }
        })
    
    def get(self, request):
        index = request.GET["index"]
        algorithm = request.GET.get("algorithm", "")
        digest = request.GET.get("digest", "")
        try:
            upload = get_object_or_404(Upload, **get_upload_lookups(request))
            if not upload.file:
                segment = get_object_or_404(UploadSegment, index=index, upload=upload)
                if not segment.file or not segment.file.storage.exists(segment.file.name):
                    raise Http404
                elif digest:
                    try:
                        self.validate_digest(digest, segment.get_digest, algorithm=algorithm)
                    except ValidationError:
                        raise Http404
        except Http404:
            return HttpResponse('', status=204)
        return HttpResponse('')
    
    def validate_user(self, request):
        user = get_user_or_none(request)
        if user is None and getattr(settings, 'UPLOADS_REQUIRE_AUTHENTICATION', True):
            raise PermissionDenied('user authentication required')
    
    def validate_session(self, request):
        if request.user.is_anonymous and not request.session.exists(request.session.session_key):
            raise PermissionDenied('user authentication or session required')
    
    def validate_digest(self, expected, actual, **kwargs):
        if expected:
            if callable(actual):
                actual = actual(**kwargs)
            if expected != actual:
                raise ValidationError("File integrity check failed! Your file transfer was likely incomplete. Please attempt the upload again.", code='invalid')
    
    def validate_segment_count(self, request=None, count=None):
        count = get_param(request, "count", coerce=int, required=False) or 0 if count is None else count
        if SEGMENT_LIMIT < count:
            raise SuspiciousOperation("Upload has too many segments!")
    
    def validate_segment_size(self, request=None, size=None):
        size = get_param(request, "segment_size", coerce=int, required=False) or 0 if size is None else size
        if SEGMENT_ALLOWABLE_SIZE < size:
            raise SuspiciousOperation("Segment is too large!")
    
    def validate_total_size(self, request=None, size=None):
        size = get_param(request, "total_size", coerce=int, required=False) or 0 if size is None else size
        if SEGMENT_ALLOWABLE_SIZE * SEGMENT_LIMIT < size:
            raise SuspiciousOperation("File is too large!")
    
    def validate_algorithm(self, algorithm):
        if algorithm and algorithm not in hasher_map.keys():
            raise SuspiciousOperation("Unsupported algorithm!")
    
    def put(self, request):
        session_key = request.session.session_key
        if not request.session.exists(session_key):
            confirm_key = 'confirm'
            if confirm_key not in request.GET:
                request.session.set_test_cookie()
                return HttpResponseRedirect('?%s' % confirm_key, status=307)
            else:
                if not request.session.test_cookie_worked():
                    raise PermissionDenied('user authentication is required because your client is unable to maintain an anonymous session')
                return HttpResponseRedirect(request.path, status=307)
        if request.session.test_cookie_worked():
            request.session.delete_test_cookie()
            status = 201
        else:
            status = 200
        return HttpResponse(session_key, status=status)
    
    def delete(self, request):
        request.session.delete()
        return HttpResponse('', status=204)
    
    def post(self, request):
        index = request.POST.get("index", "")
        filename = request.POST.get("filename", "")
        algorithm = request.POST.get("algorithm", "")
        digest = request.POST.get("digest", "")
        
        self.validate_algorithm(algorithm)

        upload, created = Upload.objects.get_or_create(
            defaults={"filename": filename},
            **get_upload_lookups(request)
        )
        upload.full_clean()
    
        if index:
            
            if upload.file:
                raise StateConflictError('already materialized')
            
            self.validate_segment_count(count=upload.segments.count())
            
            uploaded_file = request.FILES["file"]
            self.validate_segment_size(size=uploaded_file.size)
    
            segment = UploadSegment.objects.get_or_create(upload=upload, index=index)[0]
            segment.attempt_count += 1
            
            if getattr(settings, 'UPLOADS_SEGMENT_MAX_ATTEMPT_COUNT', 3) < segment.attempt_count:
                raise SuspiciousOperation("Segment has been uploaded too many times!")
            
            replace_file = True
            if segment.file:
                if digest:
                    try:
                        self.validate_digest(digest, segment.get_digest, algorithm=algorithm)
                    except ValidationError:
                        segment.file.delete(save=False)
                    except FileNotFoundError:
                        logger.warning('Encountered situation where segment %s file did not exist for upload %s when it should. Proceeding with file replacement.', segment.pk, upload.pk)
                    else:
                        replace_file = False
    
            if replace_file:
                name = '{upload}-{segment}-{index}-{attempt}-{filename}'.format(
                    upload=upload.pk,
                    segment=segment.pk,
                    index=segment.index,
                    attempt=segment.attempt_count,
                    filename=filename,
                )
                segment.file.save(name, uploaded_file, save=False)
                try:
                    segment.full_clean()
                except ValidationError:
                    segment.file.delete(save=False)
                    raise
                segment.save()
                
                if digest:
                    segment.refresh_from_db(fields=['file'])
                    self.validate_digest(digest, segment.get_digest, algorithm=algorithm)
        else:
            
            if created:
                raise SuspiciousOperation("Upload cannot be created and finalized in same request!")
            
            if not upload.file:
                try:
                    result = upload.materialize(algorithm=algorithm)
                except RedisLockError:
                    logger.exception('Unable to obtain lock for materialization of upload %s', upload.pk)
                else:
                    if result:
                        for receiver, url in result:
                            if url:
                                return HttpResponse(url, status=300)
            
            if upload.file:
                try:
                    self.validate_digest(digest, upload.digest)
                except ValidationError:
                    try:
                        upload.delete()
                    except models.ProtectedError:
                        # If we get here, the user has previously uploaded this file successfully (probably with a different client)
                        # and should be actively working with it, so we cannot just clear the other secrets. This would be an
                        # unlikely occurrence that we do not expect to actually happen. If we do get here, it is likely that the
                        # clients are using different digest algorithms with the same upload identifier. This is currently not
                        # supported. So we are catching the exception and logging it. If this becomes a common occurrence, we could
                        # add an additional step for calculating the digest and storing it separately from the upload instance. As of
                        # now, that is unnecessary and the client is to be blamed for malfunctioning. They should include the algorithm
                        # used to compute the digest in their upload identifier string.
                        message = 'Failed to cleanup after digest mismatch for protected upload %s' % upload.pk
                        logger.exception(message)
                        raise StateConflictError(message)
                    raise
                    
                secret = UploadSecret.objects.create(upload=upload)
                return HttpResponse(secret.value)
        
        return HttpResponse('')

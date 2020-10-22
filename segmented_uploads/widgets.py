import logging

from django.core.exceptions import SuspiciousOperation
from django.db import models, transaction
from django.forms.widgets import ClearableFileInput, FileInput

from .models import UploadSecret

logger = logging.getLogger(__name__)


class SegmentedFileInput(FileInput):    
    def value_from_datadict(self, data, files, name):
        value = data.get(name)
        if value and not files.get(name):
            try:
                secret = UploadSecret.objects.get(value=value)
            except UploadSecret.DoesNotExist:
                raise SuspiciousOperation('secret did not exist')
            else:
                upload = secret.upload
                files[name] = upload.uploaded_file
                def cleanup():
                    secret.delete()
                    #
                    # WE MUST USE MANUAL TRANSACTION MANAGEMENT HERE BECAUSE WE CAN
                    # ENCOUNTER ERRORS DEALING WITH FILES AFTER THE UPLOAD INSTANCE
                    # IS DELETED BUT BEFORE THE FILE IS REMOVED FROM DISK. TO MAKE
                    # SURE OUR MODELS ACCURATELY REFLECT THE DISK WE MUST ROLLBACK
                    # INCASE THE FILE WAS NOT DELETED.
                    #
                    # EXAMPLE ENCOUNTERED WHEN FILE WAS OPEN IN ANOTHER PROCESS:
                    #     OSError: [Errno 26] Text file busy
                    #
                    # THIS CAUSED FILES TO BE DELETED BUT REMAIN ON DISK! PURGE TASK
                    # WILL CLEAN THIS UP SOON.
                    #
                    sid = transaction.savepoint()
                    try:
                        upload.delete()
                        transaction.savepoint_commit(sid)
                    except Exception as e:
                        transaction.savepoint_rollback(sid)
                        if isinstance(e, models.ProtectedError):
                            logger.exception('Unable to delete protected upload %s.', upload.pk)
                        else:
                            logger.exception('Unable to delete upload %s. It will linger along with file "%s" until purged.', upload.pk, upload.file.name)
                            upload.lingering = True
                            upload.save()
                transaction.on_commit(cleanup)
        return super().value_from_datadict(data, files, name)

    def value_omitted_from_data(self, data, files, name):
        return name not in data and super().value_omitted_from_data(data, files, name)
    
    def use_required_attribute(self, initial):
        # required at time of writing pending response to https://code.djangoproject.com/ticket/31118
        return super().use_required_attribute(initial) and not initial


class ClearableSegmentedFileInput(ClearableFileInput, SegmentedFileInput):
    pass

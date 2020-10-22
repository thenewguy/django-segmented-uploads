import logging

from celery import shared_task
from redis.exceptions import LockError as RedisLockError
from segmented_uploads.models import Upload

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def materialize(self, pk, algorithm):
    exception = None
    try:
        upload = Upload.objects.get(pk=pk)
    except Exception as e:
        exception = e
    else:
        try:
            upload.materialize(force=True, algorithm=algorithm)
        except Exception as e:
            exception = e
    if exception:
        if isinstance(exception, Upload.DoesNotExist):
            message = 'Task %s was unable to retrieve upload %s'
        elif isinstance(exception, RedisLockError):
            message = 'Task %s was unable to obtain lock for materialization of upload %s'
        else:
            message = 'Task %s encountered unhandled exception processing materialization of upload %s'
        logger.exception(message, self.request.id, pk)
        raise exception
    return 'success'


@shared_task(bind=True, ignore_result=True)
def purge(self):
    try:
        count, details = Upload.purge()
    except:
        logger.exception('Suppressed exception encountered attempting to purge uploads via task %s.', self.request.id)
    else:
        lines = ["Purged {} record{} successfully via task {}.".format(
            count,
            '' if count == 1 else 's',
            self.request.id,
        )]
        if count:
            lines.append("Purge details:")
            lines.append(json.dumps(details, sort_keys=True, indent=4))
        message = '\n'.join(lines)
        logger.info(message)

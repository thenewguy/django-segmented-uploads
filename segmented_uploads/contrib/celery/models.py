from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver
from django.urls import reverse
from segmented_uploads.models import Upload
from segmented_uploads.signals import trigger_materialization

from .tasks import materialize, purge


@receiver(trigger_materialization, sender=Upload)
def queue_materialize(sender, instance, **kwargs):
    lock = kwargs.pop('lock')
    algorithm = kwargs.pop('algorithm')
    pk = str(instance.pk)
    result = materialize.delay(pk, algorithm)
    # LOCK SHOULD BE EXTENDED JUST LONGER THAN TYPICAL WAIT PLUS EXECUTION TIME TO
    # MINIMIZE THE RISK OF FLOODING THE QUEUE. TOO LONG CAUSES POOR USER EXPERIENCE
    # WHEN A TASK IS LOST OR SIMILAR ERROR OCCURS
    lock.extend(120)
    return reverse('celery-materialization-status', kwargs={'id': result.id})


@receiver(post_save, sender=Upload)
def queue_purge(sender, instance, **kwargs):
    if instance.lingering:
        purge.delay()

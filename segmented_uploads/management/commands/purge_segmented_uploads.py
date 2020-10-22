import json

from django.core.management.base import BaseCommand

from ...models import Upload


class Command(BaseCommand):
    def handle(self, *args, **options):
        self.stdout.write("Purging stale uploads")
        count, details = Upload.purge()
        if count:
            self.stdout.write("")
            self.stdout.write("Purge details:")
            self.stdout.write(json.dumps(details, sort_keys=True, indent=4))
        self.stdout.write("")
        self.stdout.write("Purge summary:")
        self.stdout.write("Purged %d records." % count)

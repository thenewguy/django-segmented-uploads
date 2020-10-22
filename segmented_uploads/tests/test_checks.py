from django.conf import settings
from django.test import SimpleTestCase, override_settings

from .. import checks as project_checks


CHECK_TUPLES = (
    ('check_segmented_upload_endpoint_url', project_checks.SEGMENTED_UPLOAD_ENDPOINT_NOT_REVERSIBLE_ERROR),
)


class ChecksEmitErrorsTests(SimpleTestCase):
    @override_settings(ROOT_URLCONF='segmented_uploads.tests.urls_empty')
    def test_errors_emitted(self):
        for check, error in CHECK_TUPLES:
            with self.subTest(check=check):
                errors = getattr(project_checks, check)(None)
                self.assertEqual(errors, [error])
    
    def test_errors_empty(self):
        for check, _ in CHECK_TUPLES:
            with self.subTest(check=check):
                errors = getattr(project_checks, check)(None)
                self.assertEqual(errors, [])

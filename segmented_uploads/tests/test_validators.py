from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from ..validators import validate_truthy_or_null


class ValidatorTests(SimpleTestCase):
    def test_validate_truthy_or_null(self):
        for value in ('', 0, False):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_truthy_or_null(value)
    
    def test_validate_truthy_or_null_message(self):
        for value, message in (
            ('', 'Provided value of "" was not truthy or null'),
            (0, 'Provided value of "0" was not truthy or null'),
            (False, 'Provided value of "False" was not truthy or null'),
        ):
            with self.subTest(value=value):
                try:
                    validate_truthy_or_null(value)
                except ValidationError as error:
                    self.assertEqual(str(error), str([message]))

from django.core.exceptions import ValidationError


def validate_truthy_or_null(value):
    if not value and value is not None:
        raise ValidationError('Provided value of "%(value)s" was not truthy or null', params={
            'value': value,
        })

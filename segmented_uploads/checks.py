from django.conf import settings
from django.core.checks import register, Error, Tags
from django.urls import reverse, NoReverseMatch


SEGMENTED_UPLOAD_ENDPOINT_NOT_REVERSIBLE_ERROR = Error(
    "View 'segmented-upload-endpoint' not reversible.",
    hint="Add 'segmented-upload-endpoint' to urlpatterns.",
    id='segmented_uploads.checks.check_segmented_upload_endpoint_url.E001',
)


@register(Tags.compatibility)
def check_segmented_upload_endpoint_url(app_configs, **kwargs):
    errors = []
    
    try:
        reverse('segmented-upload-endpoint')
    except NoReverseMatch:
        errors.append(SEGMENTED_UPLOAD_ENDPOINT_NOT_REVERSIBLE_ERROR)
    
    return errors


@register(Tags.compatibility)
def check_installed_apps(app_configs, **kwargs):
    errors = []
    
    apps = (
        'segmented_uploads',
    )
    installed_apps = settings.INSTALLED_APPS
    
    for app in apps:
        if app not in installed_apps:
            error = Error(
                "Required app '%s' is not installed." % app,
                hint="Add app to settings.INSTALLED_APPS list.",
                id='segmented_uploads.checks.check_installed_apps.%s.E001' % app,
            )
            errors.append(error)
    
    return errors

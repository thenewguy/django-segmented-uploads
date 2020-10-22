from django.urls import reverse

from segmented_uploads.widgets import SegmentedFileInput, ClearableSegmentedFileInput


class SnazzyMixin(object):
    class Media:
        css = {
            'all': (
                'https://cdn.jsdelivr.net/npm/jquery-ui@1.12.1/themes/base/core.min.css',
                'https://cdn.jsdelivr.net/npm/jquery-ui@1.12.1/themes/base/progressbar.min.css',
                'https://cdn.jsdelivr.net/npm/jquery-ui@1.12.1/themes/base/theme.min.css',
                'snazzy/handler.css',
            )
        }
        js = (
            'https://cdn.jsdelivr.net/npm/js-cookie@2.2.1/src/js.cookie.min.js',
            'https://cdn.jsdelivr.net/npm/jquery@3.4.1/dist/jquery.min.js',
            'https://cdn.jsdelivr.net/npm/jquery-ui@1.12.1/ui/widget.min.js',
            'https://cdn.jsdelivr.net/npm/jquery-ui@1.12.1/ui/widgets/progressbar.js',
            'https://cdn.jsdelivr.net/npm/es6-promise@4.2.8/dist/es6-promise.auto.min.js',
            'https://cdn.jsdelivr.net/npm/resumablejs@1.1.0/resumable.min.js',
            'https://cdn.jsdelivr.net/npm/spark-md5@3.0.0/spark-md5.min.js',
            'snazzy/handler.js',
        )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        attrs = {
            'data-segmented-upload-endpoint': reverse('segmented-upload-endpoint'),
        }
        attrs.update(self.attrs)
        self.attrs = attrs


class SnazzySegmentedFileInput(SnazzyMixin, SegmentedFileInput):
    pass


class SnazzyClearableSegmentedFileInput(SnazzyMixin, ClearableSegmentedFileInput):
    pass

from django.forms import models as model_forms
from django.views.generic.edit import CreateView, UpdateView
from segmented_uploads.contrib.snazzy.widgets import SnazzyClearableSegmentedFileInput, SnazzySegmentedFileInput

from .models import Author


EDITABLE_FIELDS = ['name', 'file', 'photo']


class WidgetMixin(object):
    def get_form_class(self):
        return model_forms.modelform_factory(self.model, fields=self.fields, widgets={
            'file': SnazzySegmentedFileInput,
            'photo': SnazzyClearableSegmentedFileInput,
        })


class AuthorCreate(WidgetMixin, CreateView):
    model = Author
    fields = EDITABLE_FIELDS


class AuthorUpdate(WidgetMixin, UpdateView):
    model = Author
    fields = EDITABLE_FIELDS
    template_name_suffix = '_update_form'

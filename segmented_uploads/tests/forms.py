from django import forms

from segmented_uploads.widgets import SegmentedFileInput


class SegmentedFileForm(forms.Form):
    file = forms.FileField(widget=SegmentedFileInput)

from django.contrib import admin

from .models import Upload, UploadSecret, UploadSegment


class UploadSecretInline(admin.TabularInline):
    model = UploadSecret
    extra = 0


class UploadSegmentInline(admin.TabularInline):
    model = UploadSegment
    extra = 0


@admin.register(Upload)
class UploadAdmin(admin.ModelAdmin):
    readonly_fields = ['file', 'digest', 'user', 'session', 'created_at']
    inlines = [UploadSecretInline, UploadSegmentInline]

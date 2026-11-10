from django.contrib import admin

from .models import Snapshot, Target


@admin.register(Target)
class TargetAdmin(admin.ModelAdmin):
    list_display = ("__str__", "kind", "category", "member", "external_id", "title_filter", "active")
    list_filter = ("kind", "category", "member", "active")
    search_fields = ("title", "external_id")
    list_editable = ("category", "member", "active")


@admin.register(Snapshot)
class SnapshotAdmin(admin.ModelAdmin):
    list_display = ("target", "metric", "value", "collected_at")
    list_filter = ("metric", "target__category")
    date_hierarchy = "collected_at"

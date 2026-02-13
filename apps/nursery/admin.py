from django.contrib import admin
from .models import DiaperInventory, DiaperLog, LactationLog


@admin.register(DiaperInventory)
class DiaperInventoryAdmin(admin.ModelAdmin):
    list_display = ("size", "quantity", "last_restock")


@admin.register(DiaperLog)
class DiaperLogAdmin(admin.ModelAdmin):
    list_display = ("profile", "reporter", "time", "waste_type", "size_label", "notes")


@admin.register(LactationLog)
class LactationLogAdmin(admin.ModelAdmin):
    list_display = (
        "profile",
        "reporter",
        "start_time",
        "end_time",
        "notes",
        "is_manual_entry",
    )

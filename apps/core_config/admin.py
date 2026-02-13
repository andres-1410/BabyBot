from django.contrib import admin
from .models import DiaperSize, GlobalSetting


@admin.register(DiaperSize)
class DiaperSizeAdmin(admin.ModelAdmin):
    list_display = ("label", "is_active", "order")


@admin.register(GlobalSetting)
class GlobalSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "description")

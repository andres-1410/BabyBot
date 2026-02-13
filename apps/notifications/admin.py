from django.contrib import admin
from .models import ScheduledEvent, UserAlertPreference


@admin.register(UserAlertPreference)
class UserAlertPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "alert_diapers",
        "alert_lactation",
        "alert_meds",
        "alert_appointments",
    )


@admin.register(ScheduledEvent)
class ScheduledEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "related_id",
        "scheduled_time",
        "payload",
        "is_sent",
        "created_at",
    )

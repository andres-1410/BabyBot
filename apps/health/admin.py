from django.contrib import admin
from .models import Appointment, MedicationLog, Treatment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "profile",
        "date",
        "specialist",
        "location",
        "notes",
        "weight_kg",
        "height_cm",
        "head_circumference_cm",
        "is_completed",
    )


@admin.register(MedicationLog)
class MedicationLogAdmin(admin.ModelAdmin):
    list_display = ("treatment", "administered_at", "administered_by", "was_late")


@admin.register(Treatment)
class TreatmentAdmin(admin.ModelAdmin):
    list_display = (
        "profile",
        "medicine_name",
        "dose",
        "frequency_hours",
        "start_date",
        "duration_days",
        "is_active",
        "created_by",
    )

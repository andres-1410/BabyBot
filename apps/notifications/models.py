from django.db import models
from apps.users.models import TelegramUser


class UserAlertPreference(models.Model):
    """Configuración individual: Qué alertas quiere recibir cada usuario"""

    user = models.OneToOneField(
        TelegramUser, on_delete=models.CASCADE, related_name="alert_preferences"
    )
    alert_diapers = models.BooleanField(default=True, verbose_name="Alerta Pañales")
    alert_lactation = models.BooleanField(default=True, verbose_name="Alerta Lactancia")
    alert_meds = models.BooleanField(default=True, verbose_name="Alerta Medicinas")
    alert_appointments = models.BooleanField(default=True, verbose_name="Alerta Citas")

    def __str__(self):
        return f"Prefs de {self.user}"


class ScheduledEvent(models.Model):
    """El reemplazo de Redis/Celery. Tareas pendientes en el tiempo."""

    class EventType(models.TextChoices):
        LACTATION_REMINDER = "LACTATION", "Recordatorio Lactancia"
        MEDICATION_REMINDER = "MEDICATION", "Recordatorio Medicina"
        APPOINTMENT_REMINDER = "APPOINTMENT", "Recordatorio Cita"
        CUSTOM = "CUSTOM", "Personalizado"

    event_type = models.CharField(max_length=20, choices=EventType.choices)
    related_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="ID del objeto relacionado (ej. ID del tratamiento)",
    )
    scheduled_time = models.DateTimeField(verbose_name="Hora programada")
    payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Datos extra para el mensaje (ej. Nombre del medicamento)",
    )
    is_sent = models.BooleanField(default=False, verbose_name="¿Enviado?")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type} - {self.scheduled_time}"

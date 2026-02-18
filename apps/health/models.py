from datetime import timedelta
from django.db import models
from apps.profiles.models import Profile
from apps.users.models import TelegramUser


class Treatment(models.Model):
    """La receta médica: Qué tomar y cada cuánto"""

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)
    medicine_name = models.CharField(max_length=200, verbose_name="Medicamento")
    dose = models.CharField(max_length=100, verbose_name="Dosis (ej. 2ml)")
    frequency_hours = models.PositiveIntegerField(verbose_name="Frecuencia (Horas)")

    start_date = models.DateTimeField(verbose_name="Fecha Inicio")
    duration_days = models.PositiveIntegerField(verbose_name="Duración (Días)")

    # Agregamos este campo calculado para facilitar consultas
    end_date = models.DateTimeField(verbose_name="Fecha Fin", blank=True, null=True)

    is_active = models.BooleanField(default=True, verbose_name="Tratamiento Activo")
    created_by = models.ForeignKey(TelegramUser, on_delete=models.SET_NULL, null=True)

    def save(self, *args, **kwargs):
        # Calcular fecha fin automáticamente al guardar
        if self.start_date and self.duration_days:
            self.end_date = self.start_date + timedelta(days=self.duration_days)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.medicine_name} para {self.profile.name}"


class MedicationLog(models.Model):
    """Registro de cada toma suministrada"""

    treatment = models.ForeignKey(
        Treatment, on_delete=models.CASCADE, related_name="logs"
    )
    administered_at = models.DateTimeField(verbose_name="Hora Suministro")
    administered_by = models.ForeignKey(
        TelegramUser, on_delete=models.SET_NULL, null=True
    )
    was_late = models.BooleanField(default=False, verbose_name="¿Fue atrasada?")

    def __str__(self):
        return f"{self.treatment.medicine_name} - {self.administered_at}"


class Appointment(models.Model):
    """Cita médica y a la vez registro de crecimiento"""

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)
    date = models.DateTimeField(verbose_name="Fecha Cita")
    specialist = models.CharField(
        max_length=100, verbose_name="Especialista (ej. Pediatra)"
    )
    location = models.CharField(max_length=200, blank=True, verbose_name="Lugar")
    notes = models.TextField(blank=True, verbose_name="Diagnóstico/Notas")

    # Datos de Crecimiento
    weight_kg = models.DecimalField(
        max_digits=5, decimal_places=3, null=True, blank=True, verbose_name="Peso (kg)"
    )
    height_cm = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Talla (cm)"
    )
    head_circumference_cm = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Perímetro Cefálico",
    )
    is_completed = models.BooleanField(default=False)

    def __str__(self):
        return f"Cita {self.specialist} - {self.date.strftime('%d/%m')}"

from django.db import models
from apps.profiles.models import Profile
from apps.users.models import TelegramUser
from apps.core_config.models import DiaperSize


class DiaperInventory(models.Model):
    """Inventario real: Cuántos pañales quedan de cada talla"""

    size = models.OneToOneField(
        DiaperSize, on_delete=models.CASCADE, verbose_name="Talla"
    )
    quantity = models.PositiveIntegerField(
        default=0, verbose_name="Cantidad Disponible"
    )
    last_restock = models.DateTimeField(auto_now=True, verbose_name="Última Recarga")

    def __str__(self):
        return f"Talla {self.size.label}: {self.quantity} pañales"


class DiaperLog(models.Model):
    """Bitácora histórica de cambios de pañal"""

    class WasteType(models.TextChoices):
        PEE = "PEE", "Pipí 💧"
        POO = "POO", "Popó 💩"
        BOTH = "BOTH", "Ambos ☣️"

    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="diaper_logs"
    )
    reporter = models.ForeignKey(
        TelegramUser, on_delete=models.SET_NULL, null=True, verbose_name="Quién reportó"
    )
    time = models.DateTimeField(verbose_name="Hora del cambio")
    waste_type = models.CharField(max_length=10, choices=WasteType.choices)
    size_label = models.CharField(
        max_length=20, verbose_name="Talla Usada"
    )  # Guardamos texto por si borran la talla en el futuro
    notes = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.profile.name} - {self.get_waste_type_display()} ({self.time.strftime('%H:%M')})"


class LactationLog(models.Model):
    """Sesiones de lactancia. Si 'end_time' es Null, la sesión está activa (cronómetro andando)"""

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)
    reporter = models.ForeignKey(TelegramUser, on_delete=models.SET_NULL, null=True)
    start_time = models.DateTimeField(verbose_name="Inicio")
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="Fin")
    notes = models.TextField(blank=True, null=True, verbose_name="Observaciones")

    # Campo calculado para saber si fue manual o cronómetro
    is_manual_entry = models.BooleanField(default=False)

    def __str__(self):
        status = "🟢 En curso" if not self.end_time else "🔴 Finalizada"
        return f"Lactancia {self.start_time.strftime('%d/%m %H:%M')} ({status})"

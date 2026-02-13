from django.db import models


class DiaperSize(models.Model):
    """Gestión dinámica de tallas (RN, P, M, G, etc.)"""

    label = models.CharField(max_length=10, unique=True, verbose_name="Etiqueta Talla")
    is_active = models.BooleanField(default=True, verbose_name="¿Disponible en menú?")
    order = models.PositiveIntegerField(
        default=0, verbose_name="Orden de visualización"
    )

    def __str__(self):
        return self.label

    class Meta:
        ordering = ["order"]
        verbose_name = "Talla de Pañal"
        verbose_name_plural = "Config: Tallas de Pañales"


class GlobalSetting(models.Model):
    """Almacén clave-valor para configuraciones editables desde el bot"""

    key = models.CharField(max_length=50, unique=True, verbose_name="Clave Config")
    value = models.CharField(max_length=255, verbose_name="Valor")
    description = models.CharField(
        max_length=255, blank=True, verbose_name="Descripción"
    )

    def __str__(self):
        return f"{self.key}: {self.value}"

    class Meta:
        verbose_name = "Configuración Global"
        verbose_name_plural = "Config: Globales"

from django.db import models


class TelegramUser(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Propietario"
        ADMIN = "ADMIN", "Administrador"
        GUEST = "GUEST", "Invitado"

    telegram_id = models.PositiveBigIntegerField(
        primary_key=True, unique=True, verbose_name="ID de Telegram"
    )
    username = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Usuario Telegram"
    )
    first_name = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Nombre Real"
    )

    # Nuestro campo personalizado para la bitácora (Ej: "Papá", "Mamá")
    nickname = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="Apodo Familiar"
    )

    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.GUEST, verbose_name="Rol"
    )
    is_active = models.BooleanField(default=True, verbose_name="¿Activo?")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nickname or self.first_name} ({self.role})"

    class Meta:
        verbose_name = "Usuario del Bot"
        verbose_name_plural = "Usuarios del Bot"

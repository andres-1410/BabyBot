from django.db import models


class Profile(models.Model):
    class ProfileType(models.TextChoices):
        BABY = "BABY", "Bebé"
        ADULT = "ADULT", "Adulto"

    name = models.CharField(max_length=100, verbose_name="Nombre del Perfil")
    profile_type = models.CharField(
        max_length=10,
        choices=ProfileType.choices,
        default=ProfileType.BABY,
        verbose_name="Tipo",
    )
    birth_date = models.DateField(verbose_name="Fecha de Nacimiento")
    created_at = models.DateTimeField(auto_now_add=True)

    # Propiedad útil para el futuro
    @property
    def is_baby(self):
        return self.profile_type == self.ProfileType.BABY

    def __str__(self):
        return f"{self.name} ({self.get_profile_type_display()})"

    class Meta:
        verbose_name = "Perfil (Paciente)"
        verbose_name_plural = "Perfiles"

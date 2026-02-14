from asgiref.sync import sync_to_async
from apps.core_config.models import GlobalSetting

# Claves constantes para evitar errores de dedo
KEY_LACTATION_INTERVAL = "lactation_interval"
KEY_DIAPER_THRESHOLD = "diaper_threshold"

# Valores por defecto
DEFAULT_LACTATION_INTERVAL = "3.0"
DEFAULT_DIAPER_THRESHOLD = "15"


async def get_setting(key, default_val):
    """Obtiene un valor de la BD, si no existe devuelve el default"""
    try:
        setting = await sync_to_async(GlobalSetting.objects.get)(key=key)
        return setting.value
    except GlobalSetting.DoesNotExist:
        return default_val


async def set_setting(key, value, description=""):
    """Guarda o actualiza un valor en la BD"""
    await sync_to_async(GlobalSetting.objects.update_or_create)(
        key=key, defaults={"value": value, "description": description}
    )

from asgiref.sync import sync_to_async
from apps.notifications.models import UserAlertPreference
from apps.users.models import TelegramUser


async def get_or_create_preferences(user_id):
    """Busca las preferencias de un usuario, si no existen las crea por defecto."""
    try:
        user = await sync_to_async(TelegramUser.objects.get)(telegram_id=user_id)
        prefs, created = await sync_to_async(UserAlertPreference.objects.get_or_create)(
            user=user
        )
        return prefs
    except TelegramUser.DoesNotExist:
        return None


async def toggle_preference(user_id, field_name):
    """Invierte el valor de una alerta específica (True <-> False)"""
    prefs = await get_or_create_preferences(user_id)
    if not prefs:
        return None, False

    # Obtenemos el valor actual dinámicamente
    current_value = getattr(prefs, field_name)
    new_value = not current_value

    # Guardamos el nuevo valor
    setattr(prefs, field_name, new_value)
    await sync_to_async(prefs.save)()

    return prefs, new_value

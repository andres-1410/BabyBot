import logging
from asgiref.sync import sync_to_async
from telegram.ext import ContextTypes
from apps.users.models import TelegramUser
from apps.notifications.models import UserAlertPreference

logger = logging.getLogger("apps.notifications")


async def send_alert(bot, topic_field, message):
    """
    Envía una alerta a todos los usuarios que tengan activada la preferencia 'topic_field'.
    Ej: topic_field='alert_diapers'
    """
    # 1. Buscar usuarios activos con la preferencia activada
    # Nota: Django ORM filter con relaciones
    prefs = await sync_to_async(list)(
        UserAlertPreference.objects.filter(
            user__is_active=True, **{topic_field: True}
        ).select_related("user")
    )

    count = 0
    for pref in prefs:
        try:
            await bot.send_message(chat_id=pref.user.telegram_id, text=message)
            count += 1
        except Exception as e:
            logger.error(f"Fallo enviando alerta a {pref.user}: {e}")

    if count > 0:
        logger.info(f"Alerta '{topic_field}' enviada a {count} usuarios.")

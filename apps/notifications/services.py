import logging
from asgiref.sync import sync_to_async
from telegram.ext import ContextTypes
from apps.users.models import TelegramUser
from apps.notifications.models import UserAlertPreference

logger = logging.getLogger("apps.notifications")


def _get_subscribers(topic_field, exclude_id=None):
    """
    Función síncrona auxiliar para consultar la BD.
    Filtra usuarios activos, con la preferencia activada y excluye al remitente si es necesario.
    """
    filters = {"user__is_active": True, topic_field: True}

    qs = UserAlertPreference.objects.filter(**filters).select_related("user")

    if exclude_id:
        qs = qs.exclude(user__telegram_id=exclude_id)

    return list(qs)


async def send_alert(bot, topic_field, message, exclude_user_id=None):
    """
    Envía una alerta a todos los usuarios suscritos a 'topic_field'.

    Args:
        bot: Instancia del bot.
        topic_field: Nombre del campo en UserAlertPreference (ej: 'alert_diapers').
        message: Texto a enviar.
        exclude_user_id: (Opcional) Telegram ID del usuario a excluir (ej. quien generó la acción).
    """
    # 1. Obtener destinatarios (Ejecutamos la consulta en hilo seguro)
    prefs = await sync_to_async(_get_subscribers)(topic_field, exclude_user_id)

    count = 0
    for pref in prefs:
        try:
            # Enviar mensaje con Markdown
            await bot.send_message(
                chat_id=pref.user.telegram_id, text=message, parse_mode="Markdown"
            )
            count += 1
        except Exception as e:
            logger.error(f"Fallo enviando alerta a {pref.user}: {e}")

    if count > 0:
        logger.info(f"Alerta '{topic_field}' enviada a {count} usuarios.")

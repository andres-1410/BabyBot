import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from asgiref.sync import sync_to_async
from apps.users.models import TelegramUser

logger = logging.getLogger("apps.telegram_bot")


async def send_admin_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /panel : Envía el link del Django Admin solo al Owner.
    Totalmente aislado del resto de la lógica.
    """
    user = update.effective_user

    # 1. Validar que el usuario sea el Owner
    is_owner = await sync_to_async(
        TelegramUser.objects.filter(
            telegram_id=user.id, role=TelegramUser.Role.OWNER
        ).exists
    )()

    # Si es tu esposa o un intruso, el bot se hace el loco
    if not is_owner:
        await update.message.reply_text("⛔ Comando desconocido.")
        return

    # 2. Tu URL real de Render (Asegúrate de que sea la correcta)
    # Render la expone automáticamente, pero la ponemos fija por seguridad
    admin_url = "https://babybot-app.onrender.com/admin"

    # 3. Botón con enlace
    keyboard = [[InlineKeyboardButton("🖥️ Abrir Panel Web", url=admin_url)]]

    await update.message.reply_text(
        "🛠️ **Acceso al Panel de Administración**\n\n"
        "Desde aquí puedes gestionar la base de datos de Django, hacer cargas masivas o corregir errores manuales.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


# Definimos el handler para exportarlo
panel_handler = CommandHandler("panel", send_admin_url)

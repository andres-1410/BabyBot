import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from asgiref.sync import sync_to_async
from apps.users.models import TelegramUser

logger = logging.getLogger("apps.telegram_bot")

# Estados de la conversación de aprobación
SELECT_ROLE, TYPE_NICKNAME = range(2)


async def start_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Paso 1: Owner pulsa 'Aprobar'. Preguntamos el Rol.
    """
    query = update.callback_query
    await query.answer()

    # Extraemos el ID del usuario a aprobar desde el callback (auth_approve_12345)
    target_user_id = int(query.data.split("_")[2])
    context.user_data["target_user_id"] = target_user_id

    # Botones para Rol
    keyboard = [
        [InlineKeyboardButton("👑 Admin (Esposa)", callback_data="ROLE_ADMIN")],
        [InlineKeyboardButton("👤 Invitado (Abuelos)", callback_data="ROLE_GUEST")],
    ]

    await query.edit_message_text(
        f"✅ Has decidido aprobar al ID `{target_user_id}`.\n\n"
        f"¿Qué **Rol** tendrá en el sistema?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return SELECT_ROLE


async def reject_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Opción: Owner pulsa 'Rechazar'.
    """
    query = update.callback_query
    await query.answer()

    target_user_id = int(query.data.split("_")[2])

    # Borramos al usuario de la BD (o lo marcamos bloqueado)
    user = await sync_to_async(TelegramUser.objects.get)(telegram_id=target_user_id)
    await sync_to_async(user.delete)()  # O user.is_active = False

    await query.edit_message_text(
        f"🚫 Solicitud del usuario {user.first_name} rechazada y eliminada."
    )

    # Opcional: Avisar al usuario rechazado
    try:
        await context.bot.send_message(
            chat_id=target_user_id, text="🚫 Tu solicitud de acceso ha sido rechazada."
        )
    except:
        pass  # El usuario pudo haber bloqueado el bot


async def save_role_ask_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Paso 2: Guardamos Rol y preguntamos Apodo.
    """
    query = update.callback_query
    await query.answer()

    role_code = query.data  # ROLE_ADMIN o ROLE_GUEST
    role = (
        TelegramUser.Role.ADMIN
        if role_code == "ROLE_ADMIN"
        else TelegramUser.Role.GUEST
    )
    context.user_data["target_role"] = role

    await query.edit_message_text(
        f"Rol seleccionado: **{role}**.\n\n"
        f"Ahora, escribe el **Apodo Familiar** para este usuario.\n"
        f"(Ej: Mamá, Tía Rosa, Abuelo):",
        parse_mode="Markdown",
    )
    return TYPE_NICKNAME


async def save_nickname_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Paso 3: Guardamos todo, activamos usuario y notificamos.
    """
    nickname = update.message.text
    target_user_id = context.user_data["target_user_id"]
    role = context.user_data["target_role"]

    try:
        # 1. Actualizar Usuario en BD
        user = await sync_to_async(TelegramUser.objects.get)(telegram_id=target_user_id)
        user.nickname = nickname
        user.role = role
        user.is_active = True  # ¡ACCESO CONCEDIDO!
        await sync_to_async(user.save)()

        # 2. Feedback al Owner
        await update.message.reply_text(
            f"✅ **Proceso Completado**\n"
            f"Usuario: {user.first_name}\n"
            f"Apodo: {nickname}\n"
            f"Rol: {role}\n"
            f"Estado: ACTIVO"
        )

        # 3. Notificar al Nuevo Usuario (El intruso ya no es intruso)
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"✅ **¡Bienvenido, {nickname}!**\n\n"
            f"Tu acceso ha sido aprobado por {update.effective_user.first_name} con el rol de **{role}**.\n"
            f"Usa /menu para ver las opciones disponibles.",
        )

    except Exception as e:
        logger.error(f"Error aprobando usuario: {e}")
        await update.message.reply_text(
            "🔴 Hubo un error guardando los datos. Revisa los logs."
        )

    return ConversationHandler.END


# --- DEFINICIÓN DEL HANDLER DE CONVERSACIÓN ---
admin_approval_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_approval, pattern=r"^auth_approve_")],
    states={
        SELECT_ROLE: [CallbackQueryHandler(save_role_ask_nickname, pattern=r"^ROLE_")],
        TYPE_NICKNAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_nickname_finish)
        ],
    },
    fallbacks=[],
    per_chat=True,  # Importante para que no se mezcle si hay varios admins (a futuro)
)

# Handler simple para el rechazo (fuera de la conversación)
rejection_handler = CallbackQueryHandler(reject_user, pattern=r"^auth_reject_")

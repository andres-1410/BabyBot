import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from asgiref.sync import sync_to_async
from apps.users.models import TelegramUser

# Logger (Capa Transversal)
logger = logging.getLogger("apps.telegram_bot")

# Estados de la conversación
ASKING_NICKNAME = 1


async def send_auth_request_to_owner(
    context: ContextTypes.DEFAULT_TYPE, user_requesting
):
    """
    Función auxiliar para enviar la alerta al Owner con botones.
    Se usa tanto para usuarios nuevos como para reintentos.
    """
    # Buscamos al Owner
    owner = await sync_to_async(
        TelegramUser.objects.filter(role=TelegramUser.Role.OWNER).first
    )()

    if owner:
        # Creamos los botones con el ID del solicitante
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Aprobar", callback_data=f"auth_approve_{user_requesting.id}"
                ),
                InlineKeyboardButton(
                    "🚫 Rechazar", callback_data=f"auth_reject_{user_requesting.id}"
                ),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Enviamos el mensaje al Owner
        try:
            await context.bot.send_message(
                chat_id=owner.telegram_id,
                text=f"🔔 **Nueva Solicitud de Acceso**\n\n"
                f"👤 Usuario: {user_requesting.first_name} (@{user_requesting.username})\n"
                f"🆔 ID: `{user_requesting.id}`\n\n"
                f"¿Qué deseas hacer?",
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            return True
        except Exception as e:
            logger.error(f"No se pudo enviar alerta al Owner: {e}")
            return False
    return False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Flujo 1.1 y 1.2: Punto de entrada /start
    """
    user = update.effective_user
    logger.info(f"Usuario {user.id} ({user.first_name}) inició el bot.")

    # Consultas a BD
    user_count = await sync_to_async(TelegramUser.objects.count)()
    user_exists = await sync_to_async(
        TelegramUser.objects.filter(telegram_id=user.id).exists
    )()

    # --- CASO A: EL USUARIO YA EXISTE EN BD ---
    if user_exists:
        db_user = await sync_to_async(TelegramUser.objects.get)(telegram_id=user.id)

        if db_user.is_active:
            # Ya está aprobado
            await update.message.reply_text(f"👋 Hola de nuevo, {db_user.nickname}.")
        else:
            # Está inactivo (Pendiente). REENVIAMOS ALERTA AL OWNER.
            await update.message.reply_text(
                "⛔ **Solicitud Pendiente**\n"
                "Tu usuario ya existe pero no ha sido aprobado.\n"
                "🔔 He vuelto a notificar al administrador."
            )
            await send_auth_request_to_owner(context, user)

        return ConversationHandler.END

    # --- CASO B: BASE DE DATOS VACÍA (PRIMER USUARIO = OWNER) ---
    if user_count == 0:
        await update.message.reply_text(
            "👑 **¡Bienvenido! Sistema Inicializado.**\n\n"
            "Se ha detectado que eres el primer usuario. Se te asignará el rol de **OWNER**.\n"
            "Para comenzar, ¿qué apodo usarás en los registros? (Ej: Papá)."
        )
        context.user_data["role"] = TelegramUser.Role.OWNER
        return ASKING_NICKNAME

    # --- CASO C: NUEVO USUARIO INVITADO (FLUJO 1.2) ---
    else:
        await update.message.reply_text(
            "⛔ **Acceso Restringido**\n"
            "Se ha enviado una solicitud al administrador."
        )

        # Crear usuario inactivo en BD
        await sync_to_async(TelegramUser.objects.create)(
            telegram_id=user.id,
            first_name=user.first_name,
            username=user.username,
            role=TelegramUser.Role.GUEST,
            is_active=False,
        )

        # Enviar alerta al Owner
        await send_auth_request_to_owner(context, user)

        return ConversationHandler.END


async def save_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Flujo 1.1: Guardar apodo del Owner"""
    nickname = update.message.text
    user = update.effective_user
    role = context.user_data.get("role", TelegramUser.Role.GUEST)

    # Crear al Owner en BD
    await sync_to_async(TelegramUser.objects.create)(
        telegram_id=user.id,
        first_name=user.first_name,
        username=user.username,
        nickname=nickname,
        role=role,
        is_active=True,
    )

    logger.info(f"Nuevo usuario registrado: {nickname} ({role})")
    await update.message.reply_text(f"✅ Configurado. Hola {nickname}.")

    return ConversationHandler.END


# Definición del manejador
onboarding_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start_command)],
    states={
        ASKING_NICKNAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_nickname)
        ],
    },
    fallbacks=[],
)

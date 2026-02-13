import logging
from telegram import Update, ReplyKeyboardRemove
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


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Flujo 1.1 y 1.2: Punto de entrada /start
    """
    user = update.effective_user
    logger.info(f"Usuario {user.id} ({user.first_name}) inició el bot.")

    # 1. Verificar si la BD está vacía (Para asignar OWNER)
    user_count = await sync_to_async(TelegramUser.objects.count)()
    user_exists = await sync_to_async(
        TelegramUser.objects.filter(telegram_id=user.id).exists
    )()

    if user_exists:
        # Ya está registrado, verificamos estado
        db_user = await sync_to_async(TelegramUser.objects.get)(telegram_id=user.id)
        if db_user.is_active:
            await update.message.reply_text(f"👋 Hola de nuevo, {db_user.nickname}.")
        else:
            await update.message.reply_text(
                "⛔ Tu solicitud sigue pendiente de aprobación."
            )
        return ConversationHandler.END

    if user_count == 0:
        # --- FLUJO 1.1: EL PROPIETARIO ---
        await update.message.reply_text(
            "👑 **¡Bienvenido! Sistema Inicializado.**\n\n"
            "Se ha detectado que eres el primer usuario. Se te asignará el rol de **OWNER**.\n"
            "Para comenzar, ¿qué apodo usarás en los registros? (Ej: Papá)."
        )
        # Guardamos temporalmente que este usuario será Owner
        context.user_data["role"] = TelegramUser.Role.OWNER
        return ASKING_NICKNAME

    else:
        # --- FLUJO 1.2: NUEVO USUARIO (Invitado/Esposa) ---
        await update.message.reply_text(
            "⛔ **Acceso Restringido**\n"
            "Se ha enviado una solicitud al administrador."
        )

        # Crear usuario inactivo
        await sync_to_async(TelegramUser.objects.create)(
            telegram_id=user.id,
            first_name=user.first_name,
            username=user.username,
            role=TelegramUser.Role.GUEST,
            is_active=False,
        )

        # Notificar al Owner (Implementación simplificada para esta fase)
        # En la fase de notificaciones haremos esto más robusto
        owner = await sync_to_async(
            TelegramUser.objects.filter(role=TelegramUser.Role.OWNER).first
        )()
        if owner:
            await context.bot.send_message(
                chat_id=owner.telegram_id,
                text=f"🔔 **Nueva Solicitud:** ID {user.id} ({user.first_name}) quiere entrar.\n"
                f"Usa /admin para gestionar usuarios.",
                # Nota: El flujo de botones Aprobar/Rechazar lo haremos en el Módulo Configuración
            )

        return ConversationHandler.END


async def save_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Flujo 1.1 (Continuación): Guardar el apodo "Papá"
    """
    nickname = update.message.text
    user = update.effective_user
    role = context.user_data.get("role", TelegramUser.Role.GUEST)

    # Guardar en BD
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


# Definición del manejador de conversación
onboarding_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start_command)],
    states={
        ASKING_NICKNAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_nickname)
        ],
    },
    fallbacks=[],
)

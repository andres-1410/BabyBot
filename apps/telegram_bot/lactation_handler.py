import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from asgiref.sync import sync_to_async
from django.utils import timezone

from apps.profiles.models import Profile
from apps.users.models import TelegramUser
from apps.nursery.business import registrar_lactancia
from apps.notifications.services import (
    send_alert,
)  # <--- Necesario para enviar la alerta
from apps.telegram_bot.keyboards import get_main_menu

logger = logging.getLogger("apps.telegram_bot")

# Estados
(
    SELECT_PROFILE,
    CHOOSE_MODE,
    TIMER_RUNNING,
    MANUAL_START,
    MANUAL_END,
    INPUT_OBSERVATION,
) = range(6)


# --- NAVEGACIÓN ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "🏠 **Menú Principal**", reply_markup=get_main_menu(), parse_mode="Markdown"
        )
    return ConversationHandler.END


# --- TAREA DE ALARMA (EL DESPERTADOR) ---
async def alarm_lactation_callback(context: ContextTypes.DEFAULT_TYPE):
    """Esta función se ejecuta automáticamente cuando el tiempo se cumple"""
    job = context.job
    profile_name = job.data.get("profile_name")

    # Enviamos la alerta usando el servicio central de notificaciones
    msg = f"🍼 **¡Hora de comer!**\n\nYa toca la siguiente toma de **{profile_name}**."
    await send_alert(context.bot, "alert_lactation", msg)


# --- INICIO ---
async def start_lactation_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    babies = await sync_to_async(list)(
        Profile.objects.filter(profile_type=Profile.ProfileType.BABY)
    )

    if len(babies) == 1:
        context.user_data["feed_profile_id"] = babies[0].id
        context.user_data["feed_profile_name"] = babies[0].name
        return await ask_mode_step(update, context)

    return ConversationHandler.END


async def ask_mode_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = context.user_data["feed_profile_name"]
    keyboard = [
        [
            InlineKeyboardButton(
                "▶️ Iniciar Ahora (Cronómetro)", callback_data="MODE_TIMER"
            )
        ],
        [InlineKeyboardButton("🕒 Registro Manual", callback_data="MODE_MANUAL")],
        [InlineKeyboardButton("🔙 Cancelar", callback_data="main_menu")],
    ]
    await update.callback_query.edit_message_text(
        f"🤱 **Lactancia: {name}**\n\n¿Cómo deseas registrar la toma?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return CHOOSE_MODE


# --- MODO CRONÓMETRO ---
async def start_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    start_time = timezone.now()
    context.user_data["feed_start_time"] = start_time
    local_start = timezone.localtime(start_time).strftime("%I:%M %p")

    keyboard = [[InlineKeyboardButton("⏹️ Terminar Toma", callback_data="STOP_TIMER")]]
    await query.edit_message_text(
        f"⏱️ **Lactancia en Curso...**\n\n"
        f"▶️ Inicio: {local_start}\n"
        f"Presiona el botón cuando termine.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return TIMER_RUNNING


async def stop_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    end_time = timezone.now()
    context.user_data["feed_end_time"] = end_time

    start_time = context.user_data["feed_start_time"]
    duration = int((end_time - start_time).total_seconds() / 60)

    await query.edit_message_text(
        f"✅ **Toma Finalizada**\n"
        f"⏱️ Duración: {duration} min.\n\n"
        f"📝 **¿Alguna observación?**\n(Escribe 'ninguna' o detalle):",
        parse_mode="Markdown",
    )
    return INPUT_OBSERVATION


# --- MODO MANUAL ---
async def start_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🕒 **Hora de Inicio**\nFormato 24hrs (Ej: `14:30`):", parse_mode="Markdown"
    )
    return MANUAL_START


async def save_manual_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        t = datetime.strptime(text, "%H:%M").time()
        now_ve = timezone.localtime()
        dt_naive = datetime.combine(now_ve.date(), t)
        start = timezone.make_aware(dt_naive, timezone.get_current_timezone())

        context.user_data["feed_start_time"] = start
        await update.message.reply_text("⏱️ **¿Cuántos minutos duró?** (Ej: `20`):")
        return MANUAL_END
    except ValueError:
        await update.message.reply_text("⚠️ Formato incorrecto. Usa HH:MM.")
        return MANUAL_START


async def save_manual_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("⚠️ Ingresa solo números.")
        return MANUAL_END

    minutes = int(text)
    start = context.user_data["feed_start_time"]
    end = start + timedelta(minutes=minutes)
    context.user_data["feed_end_time"] = end

    await update.message.reply_text(
        "📝 **¿Alguna observación?**\n(Escribe 'ninguna' o detalle):"
    )
    return INPUT_OBSERVATION


# --- FINALIZAR Y PROGRAMAR ALARMA ---
async def save_observation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    obs = update.message.text
    if obs.lower() == "ninguna":
        obs = ""

    profile_id = context.user_data["feed_profile_id"]
    profile_name = context.user_data["feed_profile_name"]
    start = context.user_data["feed_start_time"]
    end = context.user_data["feed_end_time"]
    reporter = await sync_to_async(TelegramUser.objects.get)(
        telegram_id=update.effective_user.id
    )

    # 1. Guardar en BD y calcular próxima (Lógica Negocio)
    log, next_feed = await registrar_lactancia(profile_id, start, end, reporter, obs)

    # 2. PROGRAMAR LA ALARMA (JobQueue)
    # run_once acepta datetime aware (con zona horaria), Telegram se encarga de esperar.
    context.job_queue.run_once(
        alarm_lactation_callback,
        when=next_feed,
        data={"profile_name": profile_name},
        name=f"lactation_alert_{profile_id}",  # Nombre único para poder cancelarla si hiciera falta
    )

    # Formateo para feedback
    duration = log.duration_minutes
    next_local = timezone.localtime(next_feed).strftime("%I:%M %p")

    await update.message.reply_text(
        f"✅ **Lactancia Guardada**\n\n"
        f"👶 {log.profile.name}\n"
        f"⏱️ Duración: {duration} min\n"
        f"📝 Obs: {obs if obs else 'Ninguna'}\n\n"
        f"⏰ **Próxima Toma: {next_local}**\n"
        f"🔔 *Alarma programada exitosamente.*",
        parse_mode="Markdown",
        reply_markup=get_main_menu(),
    )
    return ConversationHandler.END


# --- HANDLER ---
lactation_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_lactation_flow, pattern="^menu_lactation$")
    ],
    states={
        CHOOSE_MODE: [
            CallbackQueryHandler(start_timer, pattern="^MODE_TIMER$"),
            CallbackQueryHandler(start_manual, pattern="^MODE_MANUAL$"),
            CallbackQueryHandler(show_main_menu, pattern="^main_menu$"),
        ],
        TIMER_RUNNING: [CallbackQueryHandler(stop_timer, pattern="^STOP_TIMER$")],
        MANUAL_START: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_manual_start)
        ],
        MANUAL_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_manual_end)],
        INPUT_OBSERVATION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_observation)
        ],
    },
    fallbacks=[CallbackQueryHandler(show_main_menu, pattern="^main_menu$")],
    per_chat=True,
)

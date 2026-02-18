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
from apps.notifications.services import send_alert
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


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "🏠 **Menú Principal**", reply_markup=get_main_menu(), parse_mode="Markdown"
        )
    return ConversationHandler.END


# --- TAREA DE ALARMA (BROADCAST) ---
async def alarm_lactation_callback(context: ContextTypes.DEFAULT_TYPE):
    """Alerta global a todos los cuidadores"""
    job = context.job
    profile_name = job.data.get("profile_name")

    msg = f"🍼 **¡HORA DE COMER!**\n\nYa toca la siguiente toma de **{profile_name}**."

    # Usamos send_alert con el tag 'alert_lactation' que configuramos en el Módulo 3.2
    # Esto enviará el mensaje a TODOS los usuarios que tengan activada esa preferencia.
    await send_alert(context.bot, "alert_lactation", msg)


# --- FLUJO ---
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
        [InlineKeyboardButton("▶️ Iniciar (Cronómetro)", callback_data="MODE_TIMER")],
        [InlineKeyboardButton("🕒 Manual", callback_data="MODE_MANUAL")],
        [InlineKeyboardButton("🔙 Cancelar", callback_data="main_menu")],
    ]
    await update.callback_query.edit_message_text(
        f"🤱 **Lactancia: {name}**\n\n¿Cómo registramos?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return CHOOSE_MODE


# --- CRONÓMETRO ---
async def start_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    start_time = timezone.now()
    context.user_data["feed_start_time"] = start_time
    local = timezone.localtime(start_time).strftime("%I:%M %p")

    keyboard = [[InlineKeyboardButton("⏹️ Terminar Toma", callback_data="STOP_TIMER")]]
    await query.edit_message_text(
        f"⏱️ **Lactancia en Curso...**\n▶️ Inicio: {local}\n\nPresiona al terminar.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return TIMER_RUNNING


async def stop_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    end_time = timezone.now()
    context.user_data["feed_end_time"] = end_time
    duration = int(
        (end_time - context.user_data["feed_start_time"]).total_seconds() / 60
    )
    await query.edit_message_text(
        f"✅ **Toma Finalizada**\n⏱️ Duración: {duration} min.\n\n📝 **¿Observación?**",
        parse_mode="Markdown",
    )
    return INPUT_OBSERVATION


# --- MANUAL ---
async def start_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🕒 **Hora de Inicio (HH:MM)**:", parse_mode="Markdown"
    )
    return MANUAL_START


async def save_manual_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        t = datetime.strptime(update.message.text.strip(), "%H:%M").time()
        start = timezone.make_aware(
            datetime.combine(timezone.localtime().date(), t),
            timezone.get_current_timezone(),
        )
        context.user_data["feed_start_time"] = start
        await update.message.reply_text("⏱️ **¿Duración en minutos?** (Ej: 20):")
        return MANUAL_END
    except:
        await update.message.reply_text("⚠️ Formato incorrecto.")
        return MANUAL_START


async def save_manual_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        return MANUAL_END
    mins = int(update.message.text)
    context.user_data["feed_end_time"] = context.user_data[
        "feed_start_time"
    ] + timedelta(minutes=mins)
    await update.message.reply_text("📝 **¿Observación?**")
    return INPUT_OBSERVATION


# --- FINALIZAR (PERSISTENCIA + BROADCAST) ---
async def save_observation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    obs = update.message.text
    if obs.lower() == "ninguna":
        obs = ""

    pid = context.user_data["feed_profile_id"]
    pname = context.user_data["feed_profile_name"]
    reporter = await sync_to_async(TelegramUser.objects.get)(
        telegram_id=update.effective_user.id
    )

    log, next_feed = await registrar_lactancia(
        pid,
        context.user_data["feed_start_time"],
        context.user_data["feed_end_time"],
        reporter,
        obs,
    )

    # Programar alarma
    context.job_queue.run_once(
        alarm_lactation_callback,
        when=next_feed,
        data={"profile_name": pname},
        name=f"lactation_alert_{pid}",
    )

    # 1. Mensaje Persistente al usuario actual
    duration = log.duration_minutes
    next_local = timezone.localtime(next_feed).strftime("%I:%M %p")

    msg_history = (
        f"✅ **LACTANCIA REGISTRADA**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👶 {pname}\n"
        f"⏱️ Duración: {duration} min\n"
        f"📝 Obs: {obs or 'Ninguna'}\n"
        f"⏰ **Próxima: {next_local}**\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(msg_history, parse_mode="Markdown")
    await update.message.reply_text("🏠 Menú Principal", reply_markup=get_main_menu())

    # 2. BROADCAST (Seguridad Global)
    # Avisar a los demás que el bebé ya comió
    reporter_name = reporter.nickname or reporter.first_name
    broadcast_msg = (
        f"ℹ️ **AVISO DE LACTANCIA**\n\n"
        f"**{reporter_name}** acaba de registrar una toma.\n"
        f"👶 {pname} | ⏱️ {duration} min\n"
        f"⏰ Próxima: {next_local}"
    )
    # Enviamos a todos los que tengan alerta de lactancia (menos al que reportó, que ya vio el mensaje arriba)
    await send_alert(
        context.bot,
        "alert_lactation",
        broadcast_msg,
        exclude_user_id=reporter.telegram_id,
    )

    return ConversationHandler.END


# HANDLER
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
        MANUAL_START: [MessageHandler(filters.TEXT, save_manual_start)],
        MANUAL_END: [MessageHandler(filters.TEXT, save_manual_end)],
        INPUT_OBSERVATION: [MessageHandler(filters.TEXT, save_observation)],
    },
    fallbacks=[CallbackQueryHandler(show_main_menu, pattern="^main_menu$")],
    per_chat=True,
)

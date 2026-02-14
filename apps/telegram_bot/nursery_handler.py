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

from apps.core_config.models import DiaperSize
from apps.profiles.models import Profile
from apps.nursery.models import DiaperLog
from apps.nursery.business import registrar_uso_panal
from apps.notifications.services import send_alert
from apps.telegram_bot.keyboards import get_main_menu

logger = logging.getLogger("apps.telegram_bot")

# Estados
SELECT_PROFILE, SELECT_TIME, INPUT_MANUAL_TIME, SELECT_SIZE, SELECT_TYPE = range(5)


# --- INICIO DEL FLUJO ---
async def start_diaper_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # 1. Seleccionar Perfil (Bebé)
    # Optimizacion: Si solo hay 1 bebé, lo seleccionamos automático (Mejora UX)
    babies = await sync_to_async(list)(
        Profile.objects.filter(profile_type=Profile.ProfileType.BABY)
    )

    if not babies:
        await query.edit_message_text("⚠️ No hay perfiles de Bebé registrados.")
        return ConversationHandler.END

    if len(babies) == 1:
        # Salto directo al siguiente paso
        context.user_data["diaper_profile_id"] = babies[0].id
        context.user_data["diaper_profile_name"] = babies[0].name
        return await ask_time_step(update, context, is_new=False)

    # Si hay más de uno, mostramos botones
    keyboard = []
    for baby in babies:
        keyboard.append(
            [InlineKeyboardButton(baby.name, callback_data=f"baby_{baby.id}")]
        )

    await query.edit_message_text(
        "💩 **Registro de Pañal**\n¿A quién cambiamos?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return SELECT_PROFILE


async def save_profile_ask_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    baby_id = int(query.data.split("_")[1])
    # Guardamos nombre para feedback visual (consulta rapida)
    baby = await sync_to_async(Profile.objects.get)(id=baby_id)

    context.user_data["diaper_profile_id"] = baby_id
    context.user_data["diaper_profile_name"] = baby.name

    return await ask_time_step(update, context, is_new=False)


# --- PASO DE TIEMPO ---
async def ask_time_step(
    update: Update, context: ContextTypes.DEFAULT_TYPE, is_new=True
):
    # Helper para enviar mensaje (ya que venimos de distintas rutas)
    text = f"🕒 **Hora del Cambio ({context.user_data['diaper_profile_name']})**\n\n¿Fue ahora mismo o hace un rato?"
    keyboard = [
        [InlineKeyboardButton("▶️ Ahora Mismo", callback_data="TIME_NOW")],
        [InlineKeyboardButton("🕒 Ingresar Hora Manual", callback_data="TIME_MANUAL")],
        [InlineKeyboardButton("🔙 Cancelar", callback_data="main_menu")],
    ]

    if is_new:  # Si venimos directo del menu, editamos
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    else:  # Si venimos de la funcion start, a veces hay que editar
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
            )

    return SELECT_TIME


async def handle_time_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "TIME_NOW":
        context.user_data["diaper_time"] = (
            None  # None significa "Ahora" para el backend
        )
        return await ask_size_step(update, context)
    else:
        await query.edit_message_text(
            "🕒 **Hora Manual**\n\nIngresa la hora en formato 24hrs (Ej: `14:30` o `09:15`):",
            parse_mode="Markdown",
        )
        return INPUT_MANUAL_TIME


async def save_manual_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text.strip()
    try:
        # Validar formato HH:MM
        valid_time = datetime.strptime(time_str, "%H:%M").time()

        # Combinar con la fecha de hoy
        now = datetime.now()
        dt = datetime.combine(now.date(), valid_time)

        context.user_data["diaper_time"] = dt

        # Feedback y siguiente paso
        await update.message.reply_text(f"✅ Hora registrada: {time_str}")
        return await ask_size_step(update, context, from_msg=True)

    except ValueError:
        await update.message.reply_text("⚠️ Formato incorrecto. Usa HH:MM (Ej: 14:30):")
        return INPUT_MANUAL_TIME


# --- PASO DE TALLA ---
async def ask_size_step(
    update: Update, context: ContextTypes.DEFAULT_TYPE, from_msg=False
):
    # Buscar tallas activas
    sizes = await sync_to_async(list)(
        DiaperSize.objects.filter(is_active=True).order_by("order")
    )

    keyboard = []
    row = []
    for size in sizes:
        row.append(InlineKeyboardButton(size.label, callback_data=f"SIZE_{size.label}"))
        if len(row) == 2:  # 2 por fila
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    text = "📏 **Selecciona la Talla**:"

    if from_msg:
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    else:
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )

    return SELECT_SIZE


async def save_size_ask_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    size_label = query.data.split("_")[1]
    context.user_data["diaper_size"] = size_label

    # Preguntar Tipo
    keyboard = [
        [
            InlineKeyboardButton("💧 Pipí", callback_data="PEE"),
            InlineKeyboardButton("💩 Popó", callback_data="POO"),
        ],
        [InlineKeyboardButton("☣️ Ambos", callback_data="BOTH")],
    ]

    await query.edit_message_text(
        f"✅ Talla {size_label}.\n\n🤢 **¿Qué contenía?**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return SELECT_TYPE


# --- GUARDADO FINAL ---
async def finish_diaper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    waste_code = query.data  # PEE, POO, BOTH

    # Recuperar datos
    profile_id = context.user_data["diaper_profile_id"]
    size_label = context.user_data["diaper_size"]
    time_val = context.user_data.get("diaper_time")  # Puede ser None (Ahora) o datetime

    # Obtener el usuario de telegram (reportero) asociado al modelo TelegramUser
    from apps.users.models import TelegramUser

    reporter = await sync_to_async(TelegramUser.objects.get)(
        telegram_id=update.effective_user.id
    )

    # EJECUTAR LÓGICA DE NEGOCIO
    log, stock, alert_triggered = await registrar_uso_panal(
        profile_id=profile_id,
        size_label=size_label,
        waste_type=waste_code,
        reporter_user=reporter,
        timestamp=time_val,
    )

    # Feedback visual
    waste_icon = {"PEE": "💧 Pipí", "POO": "💩 Popó", "BOTH": "☣️ Ambos"}.get(
        waste_code, waste_code
    )

    time_str = log.time.strftime("%I:%M %p")

    msg = (
        f"✅ **Pañal Registrado**\n\n"
        f"👶 {log.profile.name}\n"
        f"🕒 {time_str}\n"
        f"📏 {size_label} | {waste_icon}\n"
        f"📦 **Stock Restante: {stock}**"
    )

    await query.edit_message_text(msg, parse_mode="Markdown")
    await query.message.reply_text("🏠 Menú Principal", reply_markup=get_main_menu())

    # ALERTA DE STOCK BAJO (Si aplica)
    if alert_triggered:
        alert_msg = f"⚠️ **¡Alerta de Pañales!**\n\nQuedan solo **{stock}** pañales talla **{size_label}**.\nEs hora de recargar."
        await send_alert(context.bot, "alert_diapers", alert_msg)

    return ConversationHandler.END


# --- FUNCIÓN DE CANCELACIÓN (LA QUE FALTABA) ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela el flujo y vuelve al menú principal"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "🏠 **Menú Principal**", reply_markup=get_main_menu(), parse_mode="Markdown"
        )
    return ConversationHandler.END


# --- HANDLER DEFINITION ---
diaper_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_diaper_flow, pattern="^menu_diaper$")],
    states={
        SELECT_PROFILE: [
            CallbackQueryHandler(save_profile_ask_time, pattern=r"^baby_")
        ],
        SELECT_TIME: [
            CallbackQueryHandler(handle_time_selection, pattern="^TIME_"),
            CallbackQueryHandler(show_main_menu, pattern="^main_menu$"),  # Cancelar
        ],
        INPUT_MANUAL_TIME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_manual_time)
        ],
        SELECT_SIZE: [CallbackQueryHandler(save_size_ask_type, pattern=r"^SIZE_")],
        SELECT_TYPE: [CallbackQueryHandler(finish_diaper, pattern=r"^(PEE|POO|BOTH)$")],
    },
    fallbacks=[CallbackQueryHandler(show_main_menu, pattern="^main_menu$")],
    per_chat=True,
)

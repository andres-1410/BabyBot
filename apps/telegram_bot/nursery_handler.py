import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from asgiref.sync import sync_to_async
from django.utils import timezone  # <--- IMPORTANTE: Para manejar la zona horaria

from apps.core_config.models import DiaperSize
from apps.profiles.models import Profile
from apps.users.models import TelegramUser
from apps.nursery.models import DiaperLog, DiaperInventory
from apps.nursery.business import registrar_uso_panal
from apps.notifications.services import send_alert
from apps.telegram_bot.keyboards import get_main_menu, get_config_menu

logger = logging.getLogger("apps.telegram_bot")

# Estados Flujo 4.1 (Uso)
SELECT_PROFILE, SELECT_TIME, INPUT_MANUAL_TIME, SELECT_SIZE, SELECT_TYPE = range(5)

# Estados Flujo 4.2 (Recarga)
SELECT_SIZE_RESTOCK, INPUT_QTY_RESTOCK = range(5, 7)


# --- FUNCIÓN AUXILIAR DE NAVEGACIÓN ---
async def back_to_config_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Regresa al menú de configuración (Fallback)"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⚙️ **Configuración**\nSelecciona una opción:",
        reply_markup=get_config_menu(),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela el flujo y vuelve al menú principal"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "🏠 **Menú Principal**", reply_markup=get_main_menu(), parse_mode="Markdown"
        )
    return ConversationHandler.END


# ==========================================
#      FLUJO 4.1: REGISTRO DE USO
# ==========================================


async def start_diaper_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # 1. Seleccionar Perfil (Bebé)
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
    baby = await sync_to_async(Profile.objects.get)(id=baby_id)

    context.user_data["diaper_profile_id"] = baby_id
    context.user_data["diaper_profile_name"] = baby.name

    return await ask_time_step(update, context, is_new=False)


async def ask_time_step(
    update: Update, context: ContextTypes.DEFAULT_TYPE, is_new=True
):
    text = f"🕒 **Hora del Cambio ({context.user_data['diaper_profile_name']})**\n\n¿Fue ahora mismo o hace un rato?"
    keyboard = [
        [InlineKeyboardButton("▶️ Ahora Mismo", callback_data="TIME_NOW")],
        [InlineKeyboardButton("🕒 Ingresar Hora Manual", callback_data="TIME_MANUAL")],
        [InlineKeyboardButton("🔙 Cancelar", callback_data="main_menu")],
    ]

    if is_new:
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    else:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
            )

    return SELECT_TIME


async def handle_time_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "TIME_NOW":
        context.user_data["diaper_time"] = None
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

        # Obtener fecha de hoy EN VENEZUELA (timezone aware)
        now_ve = timezone.localtime()

        # Combinar fecha local con hora ingresada (Naive)
        dt_naive = datetime.combine(now_ve.date(), valid_time)

        # Convertir a Aware (Consciente de zona horaria)
        # Esto le dice a Django: "Esta hora es de Venezuela"
        dt_aware = timezone.make_aware(dt_naive, timezone.get_current_timezone())

        context.user_data["diaper_time"] = dt_aware

        await update.message.reply_text(f"✅ Hora registrada: {time_str}")
        return await ask_size_step(update, context, from_msg=True)

    except ValueError:
        await update.message.reply_text("⚠️ Formato incorrecto. Usa HH:MM (Ej: 14:30):")
        return INPUT_MANUAL_TIME


async def ask_size_step(
    update: Update, context: ContextTypes.DEFAULT_TYPE, from_msg=False
):
    sizes = await sync_to_async(list)(
        DiaperSize.objects.filter(is_active=True).order_by("order")
    )

    keyboard = []
    row = []
    for size in sizes:
        row.append(InlineKeyboardButton(size.label, callback_data=f"SIZE_{size.label}"))
        if len(row) == 2:
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


async def finish_diaper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    waste_code = query.data
    profile_id = context.user_data["diaper_profile_id"]
    size_label = context.user_data["diaper_size"]
    time_val = context.user_data.get("diaper_time")

    reporter = await sync_to_async(TelegramUser.objects.get)(
        telegram_id=update.effective_user.id
    )

    log, stock, alert_triggered = await registrar_uso_panal(
        profile_id=profile_id,
        size_label=size_label,
        waste_type=waste_code,
        reporter_user=reporter,
        timestamp=time_val,
    )

    waste_icon = {"PEE": "💧 Pipí", "POO": "💩 Popó", "BOTH": "☣️ Ambos"}.get(
        waste_code, waste_code
    )

    # --- CORRECCIÓN DE HORA ---
    # Convertimos la hora UTC de la BD a Hora Local de Venezuela
    local_time = timezone.localtime(log.time)
    time_str = local_time.strftime("%I:%M %p")  # Ej: 11:50 PM

    msg = (
        f"✅ **Pañal Registrado**\n\n"
        f"👶 {log.profile.name}\n"
        f"🕒 {time_str}\n"
        f"📏 {size_label} | {waste_icon}\n"
        f"📦 **Stock Restante: {stock}**"
    )

    await query.edit_message_text(msg, parse_mode="Markdown")
    await query.message.reply_text("🏠 Menú Principal", reply_markup=get_main_menu())

    if alert_triggered:
        alert_msg = f"⚠️ **¡Alerta de Pañales!**\n\nQuedan solo **{stock}** pañales talla **{size_label}**.\nEs hora de recargar."
        await send_alert(context.bot, "alert_diapers", alert_msg)

    return ConversationHandler.END


# --- DEFINICIÓN HANDLER USO ---
diaper_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_diaper_flow, pattern="^menu_diaper$")],
    states={
        SELECT_PROFILE: [
            CallbackQueryHandler(save_profile_ask_time, pattern=r"^baby_")
        ],
        SELECT_TIME: [
            CallbackQueryHandler(handle_time_selection, pattern="^TIME_"),
            CallbackQueryHandler(show_main_menu, pattern="^main_menu$"),
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


# ==========================================
#      FLUJO 4.2: RECARGA DE INVENTARIO
# ==========================================


async def start_restock_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 1: Mostrar tallas disponibles para recargar"""
    query = update.callback_query
    await query.answer()

    sizes = await sync_to_async(list)(DiaperSize.objects.all().order_by("order"))

    keyboard = []
    row = []
    for size in sizes:
        row.append(
            InlineKeyboardButton(size.label, callback_data=f"RESTOCK_SIZE_{size.label}")
        )
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # El botón "Cancelar" ahora llama a 'menu_config' y lo manejará back_to_config_menu
    keyboard.append([InlineKeyboardButton("🔙 Cancelar", callback_data="menu_config")])

    await query.edit_message_text(
        "📦 **Recargar Inventario**\n\n¿Qué talla compraste?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return SELECT_SIZE_RESTOCK


async def save_size_ask_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 2: Guardar talla y pedir cantidad"""
    query = update.callback_query
    await query.answer()

    size_label = query.data.split("_")[2]
    context.user_data["restock_size"] = size_label

    await query.edit_message_text(
        f"📏 Talla **{size_label}** seleccionada.\n\n"
        "🔢 **¿Cuántos pañales ingresan?**\n"
        "(Escribe el número, ej: `40` o `100`)",
        parse_mode="Markdown",
    )
    return INPUT_QTY_RESTOCK


async def save_qty_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 3: Actualizar BD y confirmar"""
    qty_text = update.message.text.strip()

    if not qty_text.isdigit():
        await update.message.reply_text(
            "⚠️ Por favor ingresa solo números enteros (Ej: 40)."
        )
        return INPUT_QTY_RESTOCK

    qty_to_add = int(qty_text)
    size_label = context.user_data["restock_size"]
    user = update.effective_user

    # Lógica de BD
    size_obj = await sync_to_async(DiaperSize.objects.get)(label=size_label)
    inventory, created = await sync_to_async(DiaperInventory.objects.get_or_create)(
        size=size_obj, defaults={"quantity": 0}
    )

    inventory.quantity += qty_to_add
    await sync_to_async(inventory.save)()
    new_total = inventory.quantity

    logger.info(
        f"Inventario: {user.first_name} agregó {qty_to_add} pañales talla {size_label}. Nuevo total: {new_total}"
    )

    await update.message.reply_text(
        f"✅ **Inventario Actualizado**\n\n"
        f"📦 Talla: **{size_label}**\n"
        f"➕ Ingresaron: {qty_to_add}\n"
        f"💰 **Total Disponible: {new_total}**",
        parse_mode="Markdown",
    )

    await update.message.reply_text("⚙️ Configuración", reply_markup=get_config_menu())

    return ConversationHandler.END


# --- DEFINICIÓN HANDLER RECARGA ---
restock_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_restock_flow, pattern="^restock_diapers$")
    ],
    states={
        SELECT_SIZE_RESTOCK: [
            CallbackQueryHandler(save_size_ask_qty, pattern=r"^RESTOCK_SIZE_")
        ],
        INPUT_QTY_RESTOCK: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_qty_finish)
        ],
    },
    fallbacks=[CallbackQueryHandler(back_to_config_menu, pattern="^menu_config$")],
    per_chat=True,
)

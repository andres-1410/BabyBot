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
from django.utils import timezone

from apps.core_config.models import DiaperSize
from apps.profiles.models import Profile
from apps.users.models import TelegramUser
from apps.nursery.models import DiaperInventory
from apps.nursery.business import registrar_uso_panal
from apps.notifications.services import send_alert
from apps.telegram_bot.keyboards import get_main_menu, get_config_menu

logger = logging.getLogger("apps.telegram_bot")

# Estados
SELECT_PROFILE, SELECT_TIME, INPUT_MANUAL_TIME, SELECT_SIZE, SELECT_TYPE = range(5)
SELECT_SIZE_RESTOCK, INPUT_QTY_RESTOCK = range(5, 7)


# --- AUXILIAR ---
async def back_to_config_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⚙️ **Configuración**", reply_markup=get_config_menu(), parse_mode="Markdown"
    )
    return ConversationHandler.END


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "🏠 **Menú Principal**", reply_markup=get_main_menu(), parse_mode="Markdown"
        )
    return ConversationHandler.END


# --- FLUJO 4.1: REGISTRO DE USO ---


async def start_diaper_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    babies = await sync_to_async(list)(
        Profile.objects.filter(profile_type=Profile.ProfileType.BABY)
    )

    if not babies:
        await query.edit_message_text("⚠️ No hay perfiles de Bebé registrados.")
        return ConversationHandler.END

    if len(babies) == 1:
        context.user_data["diaper_profile_id"] = babies[0].id
        context.user_data["diaper_profile_name"] = babies[0].name
        return await ask_time_step(update, context, is_new=False)

    keyboard = [
        [InlineKeyboardButton(b.name, callback_data=f"baby_{b.id}")] for b in babies
    ]
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
        [InlineKeyboardButton("🕒 Manual", callback_data="TIME_MANUAL")],
        [InlineKeyboardButton("🔙 Cancelar", callback_data="main_menu")],
    ]

    if is_new:
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    else:
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
            "🕒 **Hora Manual (HH:MM)**:", parse_mode="Markdown"
        )
        return INPUT_MANUAL_TIME


async def save_manual_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        t = datetime.strptime(update.message.text.strip(), "%H:%M").time()
        dt = timezone.make_aware(
            datetime.combine(timezone.localtime().date(), t),
            timezone.get_current_timezone(),
        )
        context.user_data["diaper_time"] = dt
        return await ask_size_step(update, context, from_msg=True)
    except ValueError:
        await update.message.reply_text("⚠️ Formato incorrecto. Usa HH:MM.")
        return INPUT_MANUAL_TIME


async def ask_size_step(
    update: Update, context: ContextTypes.DEFAULT_TYPE, from_msg=False
):
    sizes = await sync_to_async(list)(
        DiaperSize.objects.filter(is_active=True).order_by("order")
    )
    keyboard = []
    row = []
    for s in sizes:
        row.append(InlineKeyboardButton(s.label, callback_data=f"SIZE_{s.label}"))
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
    context.user_data["diaper_size"] = query.data.split("_")[1]
    keyboard = [
        [
            InlineKeyboardButton("💧 Pipí", callback_data="PEE"),
            InlineKeyboardButton("💩 Popó", callback_data="POO"),
        ],
        [InlineKeyboardButton("☣️ Ambos", callback_data="BOTH")],
    ]
    await query.edit_message_text(
        f"✅ Talla {context.user_data['diaper_size']}.\n\n🤢 **¿Qué contenía?**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return SELECT_TYPE


async def finish_diaper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    waste = query.data
    reporter = await sync_to_async(TelegramUser.objects.get)(
        telegram_id=update.effective_user.id
    )

    log, stock, alert = await registrar_uso_panal(
        profile_id=context.user_data["diaper_profile_id"],
        size_label=context.user_data["diaper_size"],
        waste_type=waste,
        reporter_user=reporter,
        timestamp=context.user_data.get("diaper_time"),
    )

    icon = {"PEE": "💧 Pipí", "POO": "💩 Popó", "BOTH": "☣️ Ambos"}.get(waste, waste)
    time_str = timezone.localtime(log.time).strftime("%I:%M %p")

    # 1. Mensaje Persistente (Historial)
    history_msg = (
        f"✅ **PAÑAL CAMBIADO**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👶 {log.profile.name}\n"
        f"🕒 {time_str}\n"
        f"📏 {log.size_label} | {icon}\n"
        f"📦 Stock: {stock}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    # Editamos el mensaje del menú para que se transforme en el historial (limpieza visual)
    # OJO: Si prefieres que se envíe uno nuevo y se borre el menú, avísame.
    # Por ahora, editar es elegante, pero si quieres historial "eterno", mejor send_message.
    # Usemos send_message para garantizar persistencia si el usuario borra el chat.

    # Borramos el menú anterior (opcional, para limpieza)
    await query.delete_message()

    # Enviamos nuevo mensaje persistente
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=history_msg, parse_mode="Markdown"
    )

    # 2. Navegación
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🏠 Menú Principal",
        reply_markup=get_main_menu(),
    )

    if alert:
        await send_alert(
            context.bot,
            "alert_diapers",
            f"⚠️ **Alerta de Stock:** Quedan {stock} pañales talla {log.size_label}.",
        )

    return ConversationHandler.END


# --- FLUJO 4.2: RECARGA ---


async def start_restock_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sizes = await sync_to_async(list)(DiaperSize.objects.all().order_by("order"))
    keyboard = []
    row = []
    for s in sizes:
        row.append(
            InlineKeyboardButton(s.label, callback_data=f"RESTOCK_SIZE_{s.label}")
        )
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Cancelar", callback_data="menu_config")])
    await query.edit_message_text(
        "📦 **Recargar Inventario**\n\n¿Qué talla?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return SELECT_SIZE_RESTOCK


async def save_size_ask_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["restock_size"] = query.data.split("_")[2]
    await query.edit_message_text(
        f"📏 Talla **{context.user_data['restock_size']}**.\n\n🔢 **Cantidad a ingresar:**",
        parse_mode="Markdown",
    )
    return INPUT_QTY_RESTOCK


async def save_qty_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        await update.message.reply_text("⚠️ Solo números.")
        return INPUT_QTY_RESTOCK

    qty = int(update.message.text)
    size = context.user_data["restock_size"]

    size_obj = await sync_to_async(DiaperSize.objects.get)(label=size)
    inv, _ = await sync_to_async(DiaperInventory.objects.get_or_create)(
        size=size_obj, defaults={"quantity": 0}
    )
    inv.quantity += qty
    await sync_to_async(inv.save)()

    # Mensaje Persistente
    await update.message.reply_text(
        f"✅ **INVENTARIO ACTUALIZADO**\n📦 Talla: {size}\n➕ Ingreso: {qty}\n💰 Total: {inv.quantity}",
        parse_mode="Markdown",
    )

    await update.message.reply_text("⚙️ Configuración", reply_markup=get_config_menu())
    return ConversationHandler.END


# HANDLERS
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
        INPUT_MANUAL_TIME: [MessageHandler(filters.TEXT, save_manual_time)],
        SELECT_SIZE: [CallbackQueryHandler(save_size_ask_type, pattern=r"^SIZE_")],
        SELECT_TYPE: [CallbackQueryHandler(finish_diaper, pattern=r"^(PEE|POO|BOTH)$")],
    },
    fallbacks=[CallbackQueryHandler(show_main_menu, pattern="^main_menu$")],
    per_chat=True,
)

restock_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_restock_flow, pattern="^restock_diapers$")
    ],
    states={
        SELECT_SIZE_RESTOCK: [
            CallbackQueryHandler(save_size_ask_qty, pattern=r"^RESTOCK_SIZE_")
        ],
        INPUT_QTY_RESTOCK: [MessageHandler(filters.TEXT, save_qty_finish)],
    },
    fallbacks=[CallbackQueryHandler(back_to_config_menu, pattern="^menu_config$")],
    per_chat=True,
)

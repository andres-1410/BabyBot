import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from apps.telegram_bot.keyboards import get_config_menu
from apps.core_config.utils import (
    get_setting,
    set_setting,
    KEY_LACTATION_INTERVAL,
    KEY_DIAPER_THRESHOLD,
    DEFAULT_LACTATION_INTERVAL,
    DEFAULT_DIAPER_THRESHOLD,
)

# 1. Configuración del Logger
logger = logging.getLogger("apps.telegram_bot")

# Estados
EDIT_LACTATION, EDIT_THRESHOLD = range(2)


async def show_global_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el menú de Globales"""
    query = update.callback_query
    await query.answer()

    lactation_val = await get_setting(
        KEY_LACTATION_INTERVAL, DEFAULT_LACTATION_INTERVAL
    )
    threshold_val = await get_setting(KEY_DIAPER_THRESHOLD, DEFAULT_DIAPER_THRESHOLD)

    keyboard = [
        [
            InlineKeyboardButton(
                f"⏱️ Lactancia: {lactation_val} hrs", callback_data="edit_lactation"
            )
        ],
        [
            InlineKeyboardButton(
                f"📉 Umbral Pañales: {threshold_val}", callback_data="edit_threshold"
            )
        ],
        [InlineKeyboardButton("🏷️ Gestionar Tallas", callback_data="manage_sizes")],
        [InlineKeyboardButton("🔙 Volver", callback_data="menu_config")],
    ]

    await query.edit_message_text(
        "🌐 **Configuraciones Globales**\n\n"
        "Reglas del sistema para alertas y cálculos.\n"
        "Selecciona para editar:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


# --- EDICIÓN DE INTERVALO DE LACTANCIA ---


async def ask_lactation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⏱️ **Editar Intervalo de Lactancia**\n\n"
        "Ingresa el número de horas entre tomas (Ej: `3.0` o `2.5`):",
        parse_mode="Markdown",
    )
    return EDIT_LACTATION


async def save_lactation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    value = update.message.text.replace(",", ".")

    try:
        float(value)
        await set_setting(KEY_LACTATION_INTERVAL, value, "Horas entre tomas")

        logger.info(
            f"Config: Intervalo Lactancia -> {value} hrs (por {user.first_name})"
        )

        # 1. Mensaje Persistente
        await update.message.reply_text(
            f"✅ **CONFIGURACIÓN ACTUALIZADA**\n"
            f"⏱️ Nuevo intervalo: **{value} horas**",
            parse_mode="Markdown",
        )

        # 2. Navegación
        await update.message.reply_text(
            "Regresando al menú...",
            reply_markup=get_config_menu(),
        )
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un número válido (Ej: 3.0):"
        )
        return EDIT_LACTATION


# --- EDICIÓN DE UMBRAL DE PAÑALES ---


async def ask_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📉 **Editar Umbral de Alerta**\n\n"
        "¿A partir de cuántos pañales quieres la alerta de stock bajo? (Ej: `15`):",
        parse_mode="Markdown",
    )
    return EDIT_THRESHOLD


async def save_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    value = update.message.text

    if value.isdigit():
        await set_setting(KEY_DIAPER_THRESHOLD, value, "Mínimo de pañales")

        logger.info(f"Config: Umbral Pañales -> {value} (por {user.first_name})")

        # 1. Mensaje Persistente
        await update.message.reply_text(
            f"✅ **CONFIGURACIÓN ACTUALIZADA**\n"
            f"📉 Nuevo umbral de alerta: **{value} unidades**",
            parse_mode="Markdown",
        )

        # 2. Navegación
        await update.message.reply_text(
            "Regresando al menú...",
            reply_markup=get_config_menu(),
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un número entero (Ej: 15):"
        )
        return EDIT_THRESHOLD


# --- HANDLER ---
config_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(ask_lactation, pattern="^edit_lactation$"),
        CallbackQueryHandler(ask_threshold, pattern="^edit_threshold$"),
    ],
    states={
        EDIT_LACTATION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_lactation)
        ],
        EDIT_THRESHOLD: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_threshold)
        ],
    },
    fallbacks=[CallbackQueryHandler(show_global_config, pattern="^menu_config$")],
    per_chat=True,
)

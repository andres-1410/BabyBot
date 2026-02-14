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

# Estados de la conversación para editar valores
EDIT_LACTATION, EDIT_THRESHOLD = range(2)


async def show_global_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el menú de Globales con los valores actuales"""
    query = update.callback_query
    await query.answer()

    # Obtener valores actuales (Async)
    lactation_val = await get_setting(
        KEY_LACTATION_INTERVAL, DEFAULT_LACTATION_INTERVAL
    )
    threshold_val = await get_setting(KEY_DIAPER_THRESHOLD, DEFAULT_DIAPER_THRESHOLD)

    # Construir el teclado dinámico
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
        # Este botón nos llevará al siguiente paso del Módulo 3.1
        [InlineKeyboardButton("🏷️ Gestionar Tallas", callback_data="manage_sizes")],
        [InlineKeyboardButton("🔙 Volver", callback_data="menu_config")],
    ]

    await query.edit_message_text(
        "🌐 **Configuraciones Globales**\n\n"
        "Aquí defines las reglas del juego:\n"
        "• **Intervalo:** Cada cuánto come Ignacio.\n"
        "• **Umbral:** Cuándo avisar que se acaban los pañales.\n\n"
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
    value = update.message.text.replace(",", ".")  # Aceptamos coma o punto

    try:
        float(value)  # Validamos que sea número
        await set_setting(KEY_LACTATION_INTERVAL, value, "Horas entre tomas")

        # LOG DE ÉXITO
        logger.info(
            f"Configuración Actualizada: Intervalo Lactancia a {value} hrs por {user.first_name} (ID: {user.id})"
        )

        await update.message.reply_text(f"✅ Intervalo actualizado a **{value} hrs**.")

        # Volver a mostrar instrucción de menú
        await update.message.reply_text(
            "Usa /menu -> Configuración -> Globales para ver el cambio.",
            reply_markup=get_config_menu(),
        )
        return ConversationHandler.END

    except ValueError:
        # LOG DE ERROR DE VALIDACIÓN
        logger.warning(
            f"Error Validación: {user.first_name} intentó poner '{value}' en lactancia."
        )

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
        "¿A partir de cuántos pañales quieres que te avise para comprar más? (Ej: `15`):",
        parse_mode="Markdown",
    )
    return EDIT_THRESHOLD


async def save_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    value = update.message.text

    if value.isdigit():
        await set_setting(KEY_DIAPER_THRESHOLD, value, "Mínimo de pañales")

        # LOG DE ÉXITO
        logger.info(
            f"Configuración Actualizada: Umbral Pañales a {value} por {user.first_name} (ID: {user.id})"
        )

        await update.message.reply_text(
            f"✅ Umbral actualizado a **{value} unidades**."
        )
        await update.message.reply_text(
            "Usa /menu -> Configuración -> Globales para ver el cambio.",
            reply_markup=get_config_menu(),
        )
        return ConversationHandler.END
    else:
        # LOG DE ERROR DE VALIDACIÓN
        logger.warning(
            f"Error Validación: {user.first_name} intentó poner '{value}' en umbral pañales."
        )

        await update.message.reply_text(
            "⚠️ Por favor ingresa un número entero (Ej: 15):"
        )
        return EDIT_THRESHOLD


# --- HANDLER DE CONVERSACIÓN ---
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

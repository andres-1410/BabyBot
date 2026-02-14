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

# Importamos el modelo de Tallas y el handler de configuración para volver
from apps.core_config.models import DiaperSize
from apps.telegram_bot.config_handler import show_global_config

logger = logging.getLogger("apps.telegram_bot")

# Estado para agregar nueva talla
ADD_SIZE_LABEL = 1


async def show_sizes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra lista de tallas con Check/X para activar/desactivar"""
    query = update.callback_query
    await query.answer()

    # 1. Obtener todas las tallas ordenadas
    sizes = await sync_to_async(list)(DiaperSize.objects.all().order_by("order"))

    keyboard = []
    # 2. Generar botones dinámicos
    for size in sizes:
        status_icon = "✅" if size.is_active else "❌"
        # El callback lleva el ID de la talla para saber cuál switchear
        btn_text = f"{status_icon} {size.label}"
        keyboard.append(
            [InlineKeyboardButton(btn_text, callback_data=f"toggle_size_{size.id}")]
        )

    # 3. Botones de acción final
    keyboard.append(
        [InlineKeyboardButton("➕ Agregar Nueva Talla", callback_data="add_new_size")]
    )
    keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data="config_globals")])

    await query.edit_message_text(
        "🏷️ **Gestión de Tallas**\n\n"
        "Toca una talla para Activar/Desactivar.\n"
        "Solo las tallas con ✅ aparecerán en el menú diario.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def toggle_size_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Acción al tocar una talla: Cambia su estado"""
    query = update.callback_query
    # Extraer ID del callback "toggle_size_5"
    size_id = int(query.data.split("_")[2])

    try:
        size = await sync_to_async(DiaperSize.objects.get)(id=size_id)
        # Invertir estado
        size.is_active = not size.is_active
        await sync_to_async(size.save)()

        logger.info(
            f"Talla {size.label} cambiada a is_active={size.is_active} por usuario {update.effective_user.id}"
        )

        # Recargar el menú para ver el cambio visual
        await show_sizes_menu(update, context)

    except DiaperSize.DoesNotExist:
        await query.answer("Error: Esa talla ya no existe.", show_alert=True)


# --- FLUJO: AGREGAR NUEVA TALLA ---


async def ask_new_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "➕ **Nueva Talla de Pañal**\n\n"
        "Escribe la etiqueta de la talla (Ej: `XG`, `Etapa 1`, `RN`):",
        parse_mode="Markdown",
    )
    return ADD_SIZE_LABEL


async def save_new_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    label = (
        update.message.text.strip().upper()
    )  # Guardamos en mayúsculas por convención

    # Verificar si ya existe
    exists = await sync_to_async(DiaperSize.objects.filter(label=label).exists)()

    if exists:
        await update.message.reply_text("⚠️ Esa talla ya existe.")
    else:
        # Crear talla
        await sync_to_async(DiaperSize.objects.create)(
            label=label,
            is_active=True,
            order=10,  # Por defecto al final, luego se puede mejorar la ordenación
        )
        logger.info(f"Nueva talla creada: {label}")
        await update.message.reply_text(f"✅ Talla **{label}** agregada.")

    # Volver a mostrar instrucción
    await update.message.reply_text(
        "Usa /menu para volver a configurar.", reply_markup=None
    )
    return ConversationHandler.END


# --- DEFINICIÓN HANDLER ---
sizes_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(ask_new_size, pattern="^add_new_size$")],
    states={
        ADD_SIZE_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_size)]
    },
    fallbacks=[CallbackQueryHandler(show_sizes_menu, pattern="^config_globals$")],
    per_chat=True,
)

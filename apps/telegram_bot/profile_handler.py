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

# Importamos modelos y teclados
from apps.profiles.models import Profile
from apps.telegram_bot.keyboards import (
    get_profiles_menu,
    get_config_menu,
    get_main_menu,
)

logger = logging.getLogger("apps.telegram_bot")

# Estados de la conversación
ASK_NAME, ASK_TYPE, ASK_BIRTHDATE = range(3)


# --- NAVEGACIÓN DE MENÚS (Controladores visuales) ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el menú principal (Responde a /menu o botón Volver)"""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "🏠 **Menú Principal**", reply_markup=get_main_menu(), parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🏠 **Menú Principal**", reply_markup=get_main_menu(), parse_mode="Markdown"
        )


async def show_config_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⚙️ **Configuración**\nSelecciona una opción:",
        reply_markup=get_config_menu(),
        parse_mode="Markdown",
    )


async def show_profiles_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Consultamos perfiles existentes para mostrarlos (Feedback visual)
    count = await sync_to_async(Profile.objects.count)()
    text = f"👥 **Gestión de Perfiles**\nHay {count} perfil(es) registrado(s)."

    await query.edit_message_text(
        text, reply_markup=get_profiles_menu(), parse_mode="Markdown"
    )


# --- FLUJO 2.1: CREACIÓN DE PERFIL ---


async def start_add_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 1: Pedir Nombre"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 **Nuevo Perfil**\n\nPor favor, escribe el **Nombre** del perfil (Ej: Ignacio):",
        parse_mode="Markdown",
    )
    return ASK_NAME


async def save_name_ask_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 2: Guardar nombre y Pedir Tipo"""
    name = update.message.text
    context.user_data["profile_name"] = name

    # Botones para seleccionar tipo (Bebé o Adulto)
    keyboard = [
        [InlineKeyboardButton("👶 Bebé", callback_data="TYPE_BABY")],
        [InlineKeyboardButton("🧑 Adulto", callback_data="TYPE_ADULT")],
    ]
    await update.message.reply_text(
        f"✅ Nombre: {name}.\n\n¿Qué **tipo** de perfil es?\n*(Selecciona 'Bebé' para activar funciones de pañales y lactancia)*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return ASK_TYPE


async def save_type_ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 3: Guardar tipo y Pedir Fecha"""
    query = update.callback_query
    await query.answer()

    type_selection = query.data  # TYPE_BABY o TYPE_ADULT
    # Mapeamos al modelo de Django
    profile_type = (
        Profile.ProfileType.BABY
        if type_selection == "TYPE_BABY"
        else Profile.ProfileType.ADULT
    )
    context.user_data["profile_type"] = profile_type

    await query.edit_message_text(
        "📅 **Fecha de Nacimiento**\n\n"
        "Ingresa la fecha en formato **DD/MM/AAAA** (Ej: 13/02/2026):",
        parse_mode="Markdown",
    )
    return ASK_BIRTHDATE


async def save_profile_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso Final: Validar fecha, Guardar en BD y Confirmar"""
    date_text = update.message.text
    try:
        # Convertir texto a fecha
        birth_date = datetime.strptime(date_text, "%d/%m/%Y").date()

        # Recuperar datos del contexto
        name = context.user_data["profile_name"]
        p_type = context.user_data["profile_type"]

        # GUARDAR EN BD (Sync to Async)
        await sync_to_async(Profile.objects.create)(
            name=name, profile_type=p_type, birth_date=birth_date
        )

        logger.info(f"Nuevo perfil creado: {name} ({p_type})")

        await update.message.reply_text(
            f"✅ **Perfil '{name}' creado exitosamente.**\n"
            f"Tipo: {p_type}\n"
            f"Fecha: {birth_date.strftime('%d/%m/%Y')}",
            parse_mode="Markdown",
            reply_markup=get_profiles_menu(),  # Volver al menú de perfiles
        )
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text(
            "⚠️ **Formato incorrecto.**\nPor favor usa DD/MM/AAAA (Ej: 25/01/2026):"
        )
        return ASK_BIRTHDATE


# --- DEFINICIÓN DEL HANDLER ---
profile_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_add_profile, pattern="^add_profile$")],
    states={
        ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_name_ask_type)],
        ASK_TYPE: [CallbackQueryHandler(save_type_ask_date, pattern="^TYPE_")],
        ASK_BIRTHDATE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_profile_finish)
        ],
    },
    fallbacks=[CallbackQueryHandler(show_profiles_menu, pattern="^menu_config$")],
    per_chat=True,
)

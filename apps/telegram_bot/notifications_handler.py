import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, error
from telegram.ext import ContextTypes, CallbackQueryHandler
from asgiref.sync import sync_to_async
from apps.users.models import TelegramUser
from apps.notifications.utils import get_or_create_preferences, toggle_preference

# Logger (Capa Transversal)
logger = logging.getLogger("apps.telegram_bot")


async def show_users_for_notifications(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Muestra la lista de usuarios activos para configurar sus alertas"""
    query = update.callback_query
    await query.answer()

    # Obtener usuarios activos
    users = await sync_to_async(list)(TelegramUser.objects.filter(is_active=True))

    keyboard = []
    for user in users:
        # El botón lleva al menú de ese usuario específico
        label = f"{user.nickname or user.first_name} ({user.role})"
        keyboard.append(
            [
                InlineKeyboardButton(
                    label, callback_data=f"config_notif_user_{user.telegram_id}"
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data="menu_config")])

    await query.edit_message_text(
        "🔔 **Configuración de Notificaciones**\n\n"
        "Selecciona el usuario que deseas configurar:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


# --- FUNCIÓN AUXILIAR DE RENDERIZADO (DRY Principle) ---
async def render_preferences_panel(query, target_user_id):
    """
    Función encargada de construir y mostrar el panel de interruptores.
    Se usa tanto al entrar al menú como al actualizar un switch.
    """
    # 1. Obtener preferencias
    prefs = await get_or_create_preferences(target_user_id)
    if not prefs:
        await query.answer("Error: Usuario no encontrado.", show_alert=True)
        return

    # 2. Obtener nombre para el título
    target_user = await sync_to_async(TelegramUser.objects.get)(
        telegram_id=target_user_id
    )
    name = target_user.nickname or target_user.first_name

    # 3. Construir botones dinámicos (Check/Cross)
    def btn(label, field, is_active):
        icon = "✅" if is_active else "❌"
        # Callback: toggle_notif_{user_id}_{field}
        return InlineKeyboardButton(
            f"{icon} {label}", callback_data=f"toggle_notif_{target_user_id}_{field}"
        )

    keyboard = [
        [btn("Pañales", "alert_diapers", prefs.alert_diapers)],
        [btn("Lactancia", "alert_lactation", prefs.alert_lactation)],
        [btn("Medicinas", "alert_meds", prefs.alert_meds)],
        [btn("Citas Médicas", "alert_appointments", prefs.alert_appointments)],
        [
            InlineKeyboardButton(
                "🔙 Volver a Usuarios", callback_data="config_notifications"
            )
        ],
    ]

    # 4. Editar el mensaje de forma segura
    try:
        await query.edit_message_text(
            f"🔔 Preferencias para **{name}**:\n\n" "Toca para Activar/Desactivar:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
    except error.BadRequest:
        # Este error ocurre si el mensaje es idéntico al anterior.
        # Lo ignoramos silenciosamente para no romper el flujo.
        pass


# --- HANDLERS PRINCIPALES ---


async def show_user_preferences(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los switches de alerta para un usuario específico (Entrada inicial)"""
    query = update.callback_query
    # Extraer ID del usuario objetivo desde "config_notif_user_12345"
    target_user_id = int(query.data.split("_")[3])

    # Llamamos al renderizador
    await render_preferences_panel(query, target_user_id)


async def toggle_notification_setting(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Acción al pulsar un switch"""
    query = update.callback_query
    # Hacemos answer() rápido para que el relojito del botón deje de girar
    await query.answer()

    data = query.data.split("_")
    # Formato: toggle_notif_{user_id}_{field}
    target_user_id = int(data[2])
    field_name = "_".join(data[3:])  # reconstruir 'alert_diapers', etc.

    # Ejecutar cambio en BD
    prefs, new_state = await toggle_preference(target_user_id, field_name)

    if prefs:
        # LOGGING (Capa Transversal)
        editor = update.effective_user
        state_str = "ACTIVADO" if new_state else "DESACTIVADO"
        logger.info(
            f"Notificaciones: {editor.first_name} cambió {field_name} a {state_str} para el usuario ID {target_user_id}"
        )

        # REFRESCAR LA VISTA: Llamamos directamente a la función auxiliar pasando el ID
        # Ya no intentamos modificar query.data, lo cual era ilegal.
        await render_preferences_panel(query, target_user_id)
    else:
        await query.answer("Error al guardar preferencia.", show_alert=True)

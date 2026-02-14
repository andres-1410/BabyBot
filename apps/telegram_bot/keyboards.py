from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# --- MENÚ PRINCIPAL ---
def get_main_menu():
    keyboard = [
        [
            InlineKeyboardButton("💩 Pañal", callback_data="menu_diaper"),
            InlineKeyboardButton("🤱 Lactancia", callback_data="menu_lactation"),
        ],
        [
            InlineKeyboardButton("💊 Salud", callback_data="menu_health"),
            InlineKeyboardButton("📋 Resumen", callback_data="menu_summary"),
        ],
        [InlineKeyboardButton("⚙️ Configuración", callback_data="menu_config")],
    ]
    return InlineKeyboardMarkup(keyboard)


# --- MENÚ CONFIGURACIÓN (Módulo 3) ---
def get_config_menu():
    keyboard = [
        [InlineKeyboardButton("👥 Perfiles", callback_data="config_profiles")],
        [InlineKeyboardButton("🌐 Globales", callback_data="config_globals")],
        [
            InlineKeyboardButton(
                "🔔 Notificaciones", callback_data="config_notifications"
            )
        ],
        [InlineKeyboardButton("🔙 Volver", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


# --- MENÚ GESTIÓN DE PERFILES (Módulo 2) ---
def get_profiles_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Nuevo Perfil", callback_data="add_profile")],
        [InlineKeyboardButton("🔙 Volver", callback_data="menu_config")],
    ]
    return InlineKeyboardMarkup(keyboard)


# --- MENÚ REACRGA PAÑALES (Módulo 4) ---


def get_config_menu():
    keyboard = [
        [
            InlineKeyboardButton("📦 Recargar Pañales", callback_data="restock_diapers")
        ],  # <--- NUEVO BOTÓN
        [InlineKeyboardButton("👥 Perfiles", callback_data="config_profiles")],
        [InlineKeyboardButton("🌐 Globales", callback_data="config_globals")],
        [
            InlineKeyboardButton(
                "🔔 Notificaciones", callback_data="config_notifications"
            )
        ],
        [InlineKeyboardButton("🔙 Volver", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

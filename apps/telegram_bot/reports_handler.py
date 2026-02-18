import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler
from asgiref.sync import sync_to_async

from apps.profiles.models import Profile
from apps.reports.business import get_day_summary, get_what_is_next
from apps.telegram_bot.keyboards import get_main_menu

logger = logging.getLogger("apps.telegram_bot")

# Estados
SELECT_PROFILE_R = range(1)


# --- MENÚ REPORTES ---
async def show_reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    profiles = await sync_to_async(list)(Profile.objects.all())

    if len(profiles) == 1:
        context.user_data["report_profile_id"] = profiles[0].id
        context.user_data["report_profile_name"] = profiles[0].name
        return await show_actions_menu(update, context)

    keyboard = []
    for p in profiles:
        keyboard.append(
            [InlineKeyboardButton(p.name, callback_data=f"rep_prof_{p.id}")]
        )
    keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data="main_menu")])

    await query.edit_message_text(
        "📊 **Reportes y Consultas**\nSelecciona el perfil:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return SELECT_PROFILE_R


async def save_profile_r(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pid = int(query.data.split("_")[2])
    profile = await sync_to_async(Profile.objects.get)(id=pid)

    context.user_data["report_profile_id"] = pid
    context.user_data["report_profile_name"] = profile.name

    return await show_actions_menu(update, context)


async def show_actions_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = context.user_data["report_profile_name"]

    keyboard = [
        [InlineKeyboardButton("📅 Resumen de Hoy", callback_data="REP_TODAY")],
        [InlineKeyboardButton("⏳ ¿Qué Sigue?", callback_data="REP_NEXT")],
        [InlineKeyboardButton("🔙 Menú Principal", callback_data="main_menu")],
    ]

    msg = f"📊 **Consultas para {name}**\n¿Qué deseas saber?"
    if update.callback_query:
        await update.callback_query.edit_message_text(
            msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )

    return SELECT_PROFILE_R


async def report_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pid = context.user_data["report_profile_id"]
    profile = await sync_to_async(Profile.objects.get)(id=pid)

    # Obtener datos
    data = await get_day_summary(profile)

    # Construcción dinámica del mensaje
    msg = f"📅 **RESUMEN DE HOY ({data['date']})**\n👤 {profile.name}\n━━━━━━━━━━━━━━━━━━\n"

    # Solo mostramos Nursery si es Bebé
    if data["is_baby"]:
        msg += (
            f"💩 **Pañales:** {data['diapers_total']}\n"
            f"   (💧{data['pee']} | 💩{data['poo']})\n\n"
            f"🍼 **Lactancia:** {data['feedings']} tomas\n"
            f"   (Tiempo total: {data['feeding_mins']} min)\n\n"
        )

    # Medicinas van para todos
    msg += (
        f"💊 **Medicinas:** {data['meds_count']} dosis\n"
        f"   ({data['meds_names']})\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data=f"rep_prof_{pid}")]]
    await query.edit_message_text(
        msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return SELECT_PROFILE_R


async def report_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pid = context.user_data["report_profile_id"]
    profile = await sync_to_async(Profile.objects.get)(id=pid)

    events = await get_what_is_next(profile)

    if not events:
        body = "✅ ¡Todo al día! No hay pendientes inmediatos."
    else:
        body = "\n\n".join(events)

    msg = (
        f"⏳ **¿QUÉ SIGUE?**\n"
        f"👤 {profile.name}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{body}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data=f"rep_prof_{pid}")]]
    await query.edit_message_text(
        msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return SELECT_PROFILE_R


async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🏠 Menú Principal", reply_markup=get_main_menu())
    return ConversationHandler.END


# --- HANDLER ---
reports_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(show_reports_menu, pattern="^menu_status$")],
    states={
        SELECT_PROFILE_R: [
            CallbackQueryHandler(save_profile_r, pattern="^rep_prof_"),
            CallbackQueryHandler(report_today, pattern="^REP_TODAY$"),
            CallbackQueryHandler(report_next, pattern="^REP_NEXT$"),
            CallbackQueryHandler(back_to_main, pattern="^main_menu$"),
        ]
    },
    fallbacks=[CallbackQueryHandler(back_to_main, pattern="^main_menu$")],
    per_chat=True,
)

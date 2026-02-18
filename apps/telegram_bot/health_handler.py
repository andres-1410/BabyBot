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
from django.utils import timezone

from apps.profiles.models import Profile
from apps.users.models import TelegramUser
from apps.health.models import Treatment, Appointment, MedicationLog
from apps.notifications.services import send_alert
from apps.notifications.models import UserAlertPreference
from apps.health.utils import check_daily_alerts, calculate_next_dose_time
from apps.telegram_bot.keyboards import get_main_menu

logger = logging.getLogger("apps.telegram_bot")

# Estados
(
    SELECT_PROFILE_T,
    INPUT_MED,
    INPUT_DOSE,
    INPUT_FREQ,
    INPUT_DUR,
    INPUT_START_TIME,
    CONFIRM_T,
) = range(7)
SELECT_PROFILE_A, INPUT_SPEC, INPUT_DATE_A, INPUT_LOC, CONFIRM_A = range(7, 12)
INPUT_WEIGHT, INPUT_HEIGHT, INPUT_HEAD, INPUT_NOTES = range(
    12, 16
)  # Estados para resultados


# --- HELPER DATABASE ---
def get_treatment_full(t_id):
    try:
        return Treatment.objects.select_related("profile", "created_by").get(id=t_id)
    except Treatment.DoesNotExist:
        return None


# --- MENÚ DE SALUD ---
async def show_health_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    keyboard = [
        [InlineKeyboardButton("➕ Nuevo Tratamiento", callback_data="new_treatment")],
        [InlineKeyboardButton("📅 Agendar Cita", callback_data="new_appointment")],
        [InlineKeyboardButton("🔙 Volver", callback_data="main_menu")],
    ]
    msg = query.edit_message_text if query else update.message.reply_text
    await msg(
        "🏥 **Módulo de Salud**\n\nGestión de medicamentos y control de niño sano.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def cancel_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    msg = "🚫 Operación cancelada."
    if query:
        await query.edit_message_text(msg, reply_markup=None)
    else:
        await update.message.reply_text(msg)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🏠 Menú Principal",
        reply_markup=get_main_menu(),
    )
    return ConversationHandler.END


# ==============================================================================
#      LÓGICA DE ALARMAS MEDICAMENTOS (BROADCAST + APODOS)
# ==============================================================================


async def alarm_meds_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    treatment_id = job.data.get("treatment_id")
    try:
        treatment = await sync_to_async(get_treatment_full)(treatment_id)
        if not treatment or not treatment.is_active:
            return

        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Suministrar", callback_data=f"DOSE_TAKE_{treatment.id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "💤 Posponer 15m", callback_data=f"DOSE_SNOOZE_{treatment.id}"
                )
            ],
        ]
        msg = f"💊 **¡HORA DEL MEDICAMENTO!** 💊\n━━━━━━━━━━━━━━━━━━\n👤 **Paciente:** {treatment.profile.name}\n🧪 **Medicina:** {treatment.medicine_name}\n💉 **Dosis:** {treatment.dose}\n━━━━━━━━━━━━━━━━━━\n👇 *Cualquier padre puede registrarlo:*"

        users_to_notify = await sync_to_async(list)(
            UserAlertPreference.objects.filter(alert_meds=True).select_related("user")
        )
        for pref in users_to_notify:
            try:
                await context.bot.send_message(
                    chat_id=pref.user.telegram_id,
                    text=msg,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Fallo broadcast med: {e}")
    except Exception as e:
        logger.error(f"Error alarm_meds: {e}")


async def handle_dose_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        action, treatment_id = query.data.split("_")[1], int(query.data.split("_")[2])
        treatment = await sync_to_async(get_treatment_full)(treatment_id)
        if not treatment:
            await query.edit_message_text("⚠️ Tratamiento no encontrado.")
            return

        action_user = await sync_to_async(TelegramUser.objects.get)(
            telegram_id=update.effective_user.id
        )
        action_name = action_user.nickname or action_user.first_name or "Usuario"

        if action == "TAKE":
            now = timezone.localtime()
            await sync_to_async(MedicationLog.objects.create)(
                treatment=treatment, administered_at=now, administered_by=action_user
            )
            next_time = calculate_next_dose_time(treatment, last_log_time=now)

            if next_time:
                context.job_queue.run_once(
                    alarm_meds_callback,
                    when=next_time,
                    data={"treatment_id": treatment.id},
                    name=f"med_alarm_{treatment.id}",
                )
                next_str = timezone.localtime(next_time).strftime("%I:%M %p")
                feedback = f"✅ **Dosis Registrada por {action_name}**\n👤 {treatment.profile.name} — {treatment.medicine_name}\n🕒 {now.strftime('%I:%M %p')}\n🔜 Siguiente: **{next_str}**"
            else:
                treatment.is_active = False
                await sync_to_async(treatment.save)()
                feedback = (
                    f"✅ **¡Tratamiento Completado!** 🎉\nEsta fue la última dosis."
                )

            await query.edit_message_text(feedback, parse_mode="Markdown")
            await send_alert(
                context.bot,
                "alert_meds",
                f"ℹ️ **AVISO DE DOSIS**\n\n**{action_name}** ya suministró el medicamento a **{treatment.profile.name}**.\n💊 {treatment.medicine_name}",
            )

        elif action == "SNOOZE":
            context.job_queue.run_once(
                alarm_meds_callback,
                when=timedelta(minutes=15),
                data={"treatment_id": treatment.id},
                name=f"med_alarm_{treatment.id}",
            )
            await query.edit_message_text(
                f"💤 Alarma pospuesta por 15 min por {action_name}."
            )
            await send_alert(
                context.bot,
                "alert_meds",
                f"💤 **{action_name}** pospuso la medicina de **{treatment.profile.name}**.",
            )

    except Exception as e:
        logger.error(f"Error handle_dose: {e}")


# ==============================================================================
#      LÓGICA DE ALERTA POST-CITA (REGISTRO DE RESULTADOS)
# ==============================================================================


async def ask_results_alert_callback(context: ContextTypes.DEFAULT_TYPE):
    """Tarea programada para después de la cita: Pide resultados."""
    job = context.job
    appt_id = job.data.get("appt_id")

    try:
        # Buscamos la cita
        appt = await sync_to_async(Appointment.objects.select_related("profile").get)(
            id=appt_id
        )
        if appt.is_completed:
            return  # Ya se llenó, no molestar

        keyboard = [
            [
                InlineKeyboardButton(
                    "📝 Registrar Datos", callback_data=f"REG_RES_{appt.id}"
                )
            ]
        ]
        msg = (
            f"🏥 **¿Cómo les fue en la cita?**\n\n"
            f"La cita de **{appt.profile.name}** con el {appt.specialist} ya debería haber terminado.\n\n"
            f"¿Deseas registrar peso, talla y notas?"
        )

        # Enviar a todos los interesados en citas
        users = await sync_to_async(list)(
            UserAlertPreference.objects.filter(alert_appointments=True).select_related(
                "user"
            )
        )
        for pref in users:
            try:
                await context.bot.send_message(
                    chat_id=pref.user.telegram_id,
                    text=msg,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown",
                )
            except:
                pass

    except Appointment.DoesNotExist:
        pass


# --- FLUJO DE REGISTRO DE RESULTADOS (CON PROTECCIÓN DOBLE REGISTRO) ---


async def start_results_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        appt_id = int(query.data.split("_")[2])

        # 1. PORTERO DE SEGURIDAD: ¿Ya está completa?
        appt = await sync_to_async(Appointment.objects.get)(id=appt_id)
        if appt.is_completed:
            await query.edit_message_text(
                "⚠️ **Acción Denegada**\n\nEstos resultados ya fueron registrados por otro usuario.",
                parse_mode="Markdown",
            )
            return ConversationHandler.END

        context.user_data["res_appt_id"] = appt_id

        await query.edit_message_text(
            "⚖️ **Registro de Control**\n\nPor favor ingresa el **Peso** (en Kg).\n(Ej: `5.4` o escribe 'x' para saltar)",
            parse_mode="Markdown",
        )
        return INPUT_WEIGHT

    except Exception as e:
        logger.error(f"Error start_results: {e}")
        await query.edit_message_text("⚠️ Error al iniciar registro.")
        return ConversationHandler.END


async def save_weight_res(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", ".")
    context.user_data["res_weight"] = None if text.lower() == "x" else float(text)

    await update.message.reply_text(
        "📏 Ahora ingresa la **Talla** (en cm).\n(Ej: `60.5` o escribe 'x' para saltar):",
        parse_mode="Markdown",
    )
    return INPUT_HEIGHT


async def save_height_res(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", ".")
    context.user_data["res_height"] = None if text.lower() == "x" else float(text)

    await update.message.reply_text(
        "🤕 Ingresa el **Perímetro Cefálico** (en cm).\n(O escribe 'x' para saltar):",
        parse_mode="Markdown",
    )
    return INPUT_HEAD


async def save_head_res(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", ".")
    context.user_data["res_head"] = None if text.lower() == "x" else float(text)

    await update.message.reply_text(
        "📝 **Notas / Diagnóstico / Vacunas**:\n(Escribe todo lo relevante o 'x' para omitir):",
        parse_mode="Markdown",
    )
    return INPUT_NOTES


async def save_notes_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    notes = "" if text.lower() == "x" else text

    appt_id = context.user_data["res_appt_id"]
    user = await sync_to_async(TelegramUser.objects.get)(
        telegram_id=update.effective_user.id
    )
    user_name = user.nickname or user.first_name

    # Verificación final antes de guardar
    appt = await sync_to_async(Appointment.objects.select_related("profile").get)(
        id=appt_id
    )
    if appt.is_completed:
        await update.message.reply_text(
            "⚠️ Alguien más guardó los resultados mientras escribías."
        )
        return ConversationHandler.END

    appt.weight_kg = context.user_data.get("res_weight")
    appt.height_cm = context.user_data.get("res_height")
    appt.head_circumference_cm = context.user_data.get("res_head")
    appt.notes = notes
    appt.is_completed = True  # Bloqueamos futuras ediciones
    await sync_to_async(appt.save)()

    # Broadcast de Resultados
    w_str = f"{appt.weight_kg} kg" if appt.weight_kg else "-"
    h_str = f"{appt.height_cm} cm" if appt.height_cm else "-"
    msg = (
        f"✅ **RESULTADOS REGISTRADOS**\n"
        f"✍️ Por: {user_name}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **{appt.profile.name}** (Cita {appt.specialist})\n"
        f"⚖️ Peso: **{w_str}**\n"
        f"📏 Talla: **{h_str}**\n"
        f"📝 Notas: {notes or 'Sin notas'}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    # Enviar a todos
    await send_alert(context.bot, "alert_appointments", msg)
    await update.message.reply_text(
        "Guardado. Volviendo al menú...", reply_markup=get_main_menu()
    )
    return ConversationHandler.END


# ==========================================
#      FLUJO 6.1 & 6.3: CREACIÓN Y EDICIÓN
# ==========================================


# ... (start_treatment, save_profile_t, save_med, save_dose, save_freq, save_dur, handle_start_time_selection, show_treatment_summary, finish_treatment MANTENIDOS IGUAL) ...
async def start_treatment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    profiles = await sync_to_async(list)(Profile.objects.all())
    keyboard = [
        [InlineKeyboardButton(p.name, callback_data=f"ht_prof_{p.id}")]
        for p in profiles
    ]
    await query.edit_message_text(
        "💊 **Nuevo Tratamiento**\n¿Para quién?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return SELECT_PROFILE_T


async def save_profile_t(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pid = int(query.data.split("_")[2])
    profile = await sync_to_async(Profile.objects.get)(id=pid)
    context.user_data["ht_pid"] = pid
    context.user_data["ht_pname"] = profile.name
    await query.edit_message_text(
        f"💊 Medicamento para **{profile.name}**\nNombre:", parse_mode="Markdown"
    )
    return INPUT_MED


async def save_med(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ht_med"] = update.message.text
    await update.message.reply_text("💉 **Dosis** (Ej: 5ml):")
    return INPUT_DOSE


async def save_dose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ht_dose"] = update.message.text
    await update.message.reply_text(
        "⏱️ **Frecuencia (Horas)** (Ej: `8`):", parse_mode="Markdown"
    )
    return INPUT_FREQ


async def save_freq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["ht_freq"] = int(update.message.text)
        await update.message.reply_text(
            "📅 **Duración (Días)**:", parse_mode="Markdown"
        )
        return INPUT_DUR
    except ValueError:
        await update.message.reply_text("⚠️ Solo números.")
        return INPUT_FREQ


async def save_dur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["ht_dur"] = int(update.message.text)
        keyboard = [
            [
                InlineKeyboardButton("▶️ Ahora Mismo", callback_data="START_NOW"),
                InlineKeyboardButton("🕒 Hora Manual", callback_data="START_MANUAL"),
            ]
        ]
        await update.message.reply_text(
            "🕒 **¿Cuándo fue la primera dosis?**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return INPUT_START_TIME
    except ValueError:
        await update.message.reply_text("⚠️ Solo números.")
        return INPUT_DUR


async def handle_start_time_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if query:
        await query.answer()
        if query.data == "START_NOW":
            return await show_treatment_summary(update, context, timezone.localtime())
        elif query.data == "START_MANUAL":
            await query.edit_message_text("🕒 Hora (HH:MM):")
            return INPUT_START_TIME
    else:
        text = update.message.text.strip()
        try:
            t = datetime.strptime(text, "%H:%M").time()
            now = timezone.localtime()
            start = timezone.make_aware(
                datetime.combine(now.date(), t), timezone.get_current_timezone()
            )
            return await show_treatment_summary(update, context, start)
        except ValueError:
            await update.message.reply_text("⚠️ Usa HH:MM.")
            return INPUT_START_TIME


async def show_treatment_summary(
    update: Update, context: ContextTypes.DEFAULT_TYPE, start_dt
):
    context.user_data["ht_start"] = start_dt
    data = context.user_data
    freq = data["ht_freq"]
    schedule = ""
    curr = start_dt
    for i in range(1, 4):
        curr += timedelta(hours=freq)
        schedule += f"• {curr.strftime('%I:%M %p')}\n"

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirmar", callback_data="CONFIRM_T"),
            InlineKeyboardButton("🚫 Cancelar", callback_data="CANCEL_T"),
        ]
    ]
    msg = f"📋 **RESUMEN**\n👤 {data['ht_pname']}\n💊 {data['ht_med']}\n💉 {data['ht_dose']}\n⏱️ Cada {freq}h\n📅 {data['ht_dur']} días\n▶️ {start_dt.strftime('%I:%M %p')}\n\n📅 **Próximas:**\n{schedule}"

    if update.callback_query:
        await update.callback_query.edit_message_text(
            msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    return CONFIRM_T


async def finish_treatment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data
    user = await sync_to_async(TelegramUser.objects.get)(
        telegram_id=update.effective_user.id
    )
    creator_name = user.nickname or user.first_name or "Usuario"
    profile = await sync_to_async(Profile.objects.get)(id=data["ht_pid"])

    t = await sync_to_async(Treatment.objects.create)(
        profile=profile,
        medicine_name=data["ht_med"],
        dose=data["ht_dose"],
        frequency_hours=data["ht_freq"],
        duration_days=data["ht_dur"],
        start_date=data["ht_start"],
        created_by=user,
    )
    next_alarm = calculate_next_dose_time(t, last_log_time=None)
    if next_alarm:
        context.job_queue.run_once(
            alarm_meds_callback,
            when=next_alarm,
            data={"treatment_id": t.id},
            name=f"med_alarm_{t.id}",
        )

    await query.edit_message_text(f"✅ **Tratamiento Creado**", parse_mode="Markdown")
    persistent_msg = f"🆕 **NUEVO TRATAMIENTO**\n━━━━━━━━━━━━━━━━━━\n👤 **{profile.name}**\n💊 {data['ht_med']} ({data['ht_dose']})\n⏱️ Cada {data['ht_freq']}h por {data['ht_dur']} días\n✍️ **Registrado por:** {creator_name}\n━━━━━━━━━━━━━━━━━━\n🔔 *Alarmas activadas para todos.*"

    users_to_notify = await sync_to_async(list)(
        UserAlertPreference.objects.filter(alert_meds=True).select_related("user")
    )
    for pref in users_to_notify:
        try:
            await context.bot.send_message(
                chat_id=pref.user.telegram_id,
                text=persistent_msg,
                parse_mode="Markdown",
            )
        except:
            pass

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🏠 Menú Principal",
        reply_markup=get_main_menu(),
    )
    return ConversationHandler.END


# ... (start_appointment, save_profile_a, save_spec, save_date_a, save_loc MANTENIDOS IGUAL) ...
async def start_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    profiles = await sync_to_async(list)(Profile.objects.all())
    keyboard = [
        [InlineKeyboardButton(p.name, callback_data=f"ha_prof_{p.id}")]
        for p in profiles
    ]
    await query.edit_message_text(
        "📅 **Nueva Cita**\n¿Para quién?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return SELECT_PROFILE_A


async def save_profile_a(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pid = int(query.data.split("_")[2])
    context.user_data["ha_pid"] = pid
    p = await sync_to_async(Profile.objects.get)(id=pid)
    context.user_data["ha_pname"] = p.name
    await query.edit_message_text("👨‍⚕️ **Especialista**:", parse_mode="Markdown")
    return INPUT_SPEC


async def save_spec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ha_spec"] = update.message.text
    await update.message.reply_text(
        "📅 **Fecha y Hora** (DD/MM/AAAA HH:MM):", parse_mode="Markdown"
    )
    return INPUT_DATE_A


async def save_date_a(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        dt_naive = datetime.strptime(text, "%d/%m/%Y %H:%M")
        dt_aware = timezone.make_aware(dt_naive, timezone.get_current_timezone())
        context.user_data["ha_date"] = dt_aware
        await update.message.reply_text("📍 **Lugar** ('no' para omitir):")
        return INPUT_LOC
    except ValueError:
        await update.message.reply_text("⚠️ Formato incorrecto.")
        return INPUT_DATE_A


async def save_loc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.text
    if loc.lower() == "no":
        loc = ""
    context.user_data["ha_loc"] = loc
    data = context.user_data
    date_str = data["ha_date"].strftime("%d/%m/%Y %I:%M %p")
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirmar", callback_data="CONFIRM_A"),
            InlineKeyboardButton("🚫 Cancelar", callback_data="CANCEL_A"),
        ]
    ]
    msg = f"📅 **CONFIRMAR CITA**\n\n👤 **{data['ha_pname']}**\n👨‍⚕️ **Especialista:** {data['ha_spec']}\n🕒 **Fecha:** {date_str}\n📍 **Lugar:** {loc or 'N/A'}"
    await update.message.reply_text(
        msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return CONFIRM_A


async def finish_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data
    profile = await sync_to_async(Profile.objects.get)(id=data["ha_pid"])
    loc = data.get("ha_loc", "")

    appt = await sync_to_async(Appointment.objects.create)(
        profile=profile, specialist=data["ha_spec"], date=data["ha_date"], location=loc
    )

    # ALERTA POST-CITA (2 horas despues) para llenar resultados
    when_ask_results = data["ha_date"] + timedelta(minutes=15)  # hours=2
    context.job_queue.run_once(
        ask_results_alert_callback,
        when=when_ask_results,
        data={"appt_id": appt.id},
        name=f"res_appt_{appt.id}",
    )

    await query.edit_message_text(f"✅ **Cita Agendada**", parse_mode="Markdown")

    # BROADCAST DE CREACIÓN DE CITA (NUEVO)
    date_str = data["ha_date"].strftime("%d/%m/%Y %I:%M %p")
    persistent_msg = f"📅 **NUEVA CITA REGISTRADA**\n━━━━━━━━━━━━━━━━━━\n👤 **{profile.name}**\n👨‍⚕️ **{data['ha_spec']}**\n🕒 **{date_str}**\n📍 {loc or 'No especificado'}\n━━━━━━━━━━━━━━━━━━\n🔔 *Todos los padres serán notificados.*"

    users = await sync_to_async(list)(
        UserAlertPreference.objects.filter(alert_appointments=True).select_related(
            "user"
        )
    )
    for pref in users:
        try:
            await context.bot.send_message(
                chat_id=pref.user.telegram_id,
                text=persistent_msg,
                parse_mode="Markdown",
            )
        except:
            pass

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🏠 Menú Principal",
        reply_markup=get_main_menu(),
    )
    return ConversationHandler.END


async def daily_appointment_check(context: ContextTypes.DEFAULT_TYPE):
    messages = await check_daily_alerts()
    if messages:
        for msg in messages:
            await send_alert(context.bot, "alert_appointments", msg)


# HANDLERS
treatment_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_treatment, pattern="^new_treatment$")],
    states={
        SELECT_PROFILE_T: [CallbackQueryHandler(save_profile_t, pattern="^ht_prof_")],
        INPUT_MED: [MessageHandler(filters.TEXT, save_med)],
        INPUT_DOSE: [MessageHandler(filters.TEXT, save_dose)],
        INPUT_FREQ: [MessageHandler(filters.TEXT, save_freq)],
        INPUT_DUR: [MessageHandler(filters.TEXT, save_dur)],
        INPUT_START_TIME: [
            CallbackQueryHandler(handle_start_time_selection, pattern="^START_"),
            MessageHandler(filters.TEXT, handle_start_time_selection),
        ],
        CONFIRM_T: [
            CallbackQueryHandler(finish_treatment, pattern="^CONFIRM_T$"),
            CallbackQueryHandler(cancel_health, pattern="^CANCEL_T$"),
        ],
    },
    fallbacks=[CallbackQueryHandler(cancel_health, pattern="^main_menu$")],
    per_chat=True,
)

appointment_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_appointment, pattern="^new_appointment$")],
    states={
        SELECT_PROFILE_A: [CallbackQueryHandler(save_profile_a, pattern="^ha_prof_")],
        INPUT_SPEC: [MessageHandler(filters.TEXT, save_spec)],
        INPUT_DATE_A: [MessageHandler(filters.TEXT, save_date_a)],
        INPUT_LOC: [MessageHandler(filters.TEXT, save_loc)],
        CONFIRM_A: [
            CallbackQueryHandler(finish_appointment, pattern="^CONFIRM_A$"),
            CallbackQueryHandler(cancel_health, pattern="^CANCEL_A$"),
        ],
    },
    fallbacks=[CallbackQueryHandler(cancel_health, pattern="^main_menu$")],
    per_chat=True,
)

results_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_results_flow, pattern="^REG_RES_")],
    states={
        INPUT_WEIGHT: [MessageHandler(filters.TEXT, save_weight_res)],
        INPUT_HEIGHT: [MessageHandler(filters.TEXT, save_height_res)],
        INPUT_HEAD: [MessageHandler(filters.TEXT, save_head_res)],
        INPUT_NOTES: [MessageHandler(filters.TEXT, save_notes_finish)],
    },
    fallbacks=[CallbackQueryHandler(cancel_health, pattern="^main_menu$")],
    per_chat=True,
)

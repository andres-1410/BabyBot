from datetime import timedelta
from django.utils import timezone
from asgiref.sync import sync_to_async
from apps.health.models import Appointment


def calculate_next_dose_time(treatment, last_log_time=None):
    """
    Calcula la hora de la siguiente dosis.
    Si la hora calculada ya pasó, avanza intervalos hasta encontrar una futura.
    """
    if not last_log_time:
        base_time = treatment.start_date
    else:
        base_time = last_log_time

    # 1. Calculamos la teórica siguiente
    next_time = base_time + timedelta(hours=treatment.frequency_hours)

    # 2. CORRECCIÓN: Ajuste de tiempo ("Catch-up")
    # Si next_time es menor o igual a "ahora", seguimos sumando horas
    # hasta caer en el futuro.
    now = timezone.localtime()

    # Solo aplicamos esto si no estamos registrando una toma atrasada intencional
    # (Para alarmas automáticas es vital).
    while next_time <= now:
        next_time += timedelta(hours=treatment.frequency_hours)

    # 3. Validar fin del tratamiento
    if treatment.end_date and next_time > treatment.end_date:
        return None

    return next_time


async def check_daily_alerts():
    """
    Busca citas médicas y genera mensajes DETALLADOS.
    """
    now = timezone.localtime()
    today = now.date()
    target_tomorrow = today + timedelta(days=1)
    target_week = today + timedelta(days=7)

    print(f"\n🔍 [DEBUG] Iniciando chequeo de alertas... {today}")

    notifications = []

    # --- 1. ALERTA: HOY (URGENTE) ---
    appts_today = await sync_to_async(list)(
        Appointment.objects.filter(is_completed=False, date__date=today).select_related(
            "profile"
        )
    )
    for appt in appts_today:
        time_str = timezone.localtime(appt.date).strftime("%I:%M %p")
        msg = (
            f"🚨 **¡HOY TIENES CITA!** 🚨\n\n"
            f"👤 **Paciente:** {appt.profile.name}\n"
            f"👨‍⚕️ **Especialista:** {appt.specialist}\n"
            f"🕒 **Hora:** {time_str}\n"
            f"📍 **Lugar:** {appt.location or 'No especificado'}\n\n"
            f"⚠️ *No olvides los documentos necesarios.*"
        )
        notifications.append(msg)

    # --- 2. ALERTA: MAÑANA (RECORDATORIO) ---
    appts_tomorrow = await sync_to_async(list)(
        Appointment.objects.filter(
            is_completed=False, date__date=target_tomorrow
        ).select_related("profile")
    )
    for appt in appts_tomorrow:
        time_str = timezone.localtime(appt.date).strftime("%I:%M %p")
        msg = (
            f"⏰ **RECORDATORIO: CITA MAÑANA**\n\n"
            f"👤 **Paciente:** {appt.profile.name}\n"
            f"👨‍⚕️ **Especialista:** {appt.specialist}\n"
            f"🕒 **Hora:** {time_str}\n"
            f"📍 **Lugar:** {appt.location or 'No especificado'}"
        )
        notifications.append(msg)

    # --- 3. ALERTA: 1 SEMANA (PLANIFICACIÓN) ---
    appts_week = await sync_to_async(list)(
        Appointment.objects.filter(
            is_completed=False, date__date=target_week
        ).select_related("profile")
    )
    for appt in appts_week:
        date_str = timezone.localtime(appt.date).strftime("%d/%m a las %I:%M %p")
        msg = (
            f"📅 **PLANIFICACIÓN SEMANAL**\n\n"
            f"En 7 días tienes un compromiso:\n"
            f"👤 **{appt.profile.name}** con {appt.specialist}\n"
            f"🗓️ **Fecha:** {date_str}"
        )
        notifications.append(msg)

    print(f"📤 [DEBUG] Alertas generadas: {len(notifications)}\n")
    return notifications

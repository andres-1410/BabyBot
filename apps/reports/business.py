from datetime import timedelta
from django.utils import timezone
from asgiref.sync import sync_to_async

from apps.profiles.models import Profile
from apps.nursery.models import DiaperLog, FeedingLog
from apps.health.models import MedicationLog, Treatment, Appointment
from apps.health.utils import calculate_next_dose_time
from apps.core_config.utils import (
    get_setting,
    KEY_LACTATION_INTERVAL,
    DEFAULT_LACTATION_INTERVAL,
)


async def get_day_summary(profile, date_obj=None):
    """Genera el resumen filtrando por tipo de perfil (Adulto vs Bebé)"""
    if not date_obj:
        date_obj = timezone.localtime().date()

    # Datos base (Medicinas aplican a todos)
    meds = await sync_to_async(list)(
        MedicationLog.objects.filter(
            treatment__profile=profile, administered_at__date=date_obj
        ).select_related("treatment")
    )
    meds_count = len(meds)
    meds_names = ", ".join(set([m.treatment.medicine_name for m in meds])) or "Ninguna"

    # Estructura base
    data = {
        "date": date_obj.strftime("%d/%m/%Y"),
        "is_baby": profile.profile_type == Profile.ProfileType.BABY,
        "meds_count": meds_count,
        "meds_names": meds_names,
        # Valores por defecto para adultos
        "diapers_total": 0,
        "pee": 0,
        "poo": 0,
        "feedings": 0,
        "feeding_mins": 0,
    }

    # Si es BEBÉ, calculamos Nursery
    if data["is_baby"]:
        # Pañales
        diapers = await sync_to_async(list)(
            DiaperLog.objects.filter(profile=profile, time__date=date_obj)
        )
        data["diapers_total"] = len(diapers)
        data["pee"] = sum(1 for d in diapers if d.waste_type in ["PEE", "BOTH"])
        data["poo"] = sum(1 for d in diapers if d.waste_type in ["POO", "BOTH"])

        # Lactancia
        feedings = await sync_to_async(list)(
            FeedingLog.objects.filter(profile=profile, start_time__date=date_obj)
        )
        data["feedings"] = len(feedings)
        data["feeding_mins"] = sum(f.duration_minutes for f in feedings)

    return data


async def get_what_is_next(profile):
    """Calcula eventos pendientes (Todas las dosis de hoy + Citas futuras)"""
    now = timezone.localtime()
    today = now.date()
    events = []

    # 1. LACTANCIA (Solo Bebés)
    if profile.profile_type == Profile.ProfileType.BABY:
        last_feed = await sync_to_async(
            lambda: FeedingLog.objects.filter(profile=profile)
            .order_by("-end_time")
            .first()
        )()

        if last_feed:
            interval_str = await get_setting(
                KEY_LACTATION_INTERVAL, DEFAULT_LACTATION_INTERVAL
            )
            interval_hours = float(interval_str)
            next_feed_time = last_feed.end_time + timedelta(hours=interval_hours)

            time_str = timezone.localtime(next_feed_time).strftime("%I:%M %p")
            status = "🔴 Atrasada desde:" if next_feed_time < now else "🟢 Toca a las:"
            events.append(f"🍼 **Lactancia:**\n{status} **{time_str}**")
        else:
            events.append("🍼 **Lactancia:** Sin registros previos.")

    # 2. PRÓXIMAS MEDICINAS (Iterar dosis restantes del día)
    active_treatments = await sync_to_async(list)(
        Treatment.objects.filter(profile=profile, is_active=True)
    )

    for t in active_treatments:
        last_log = await sync_to_async(
            lambda: t.logs.order_by("-administered_at").first()
        )()
        last_time = last_log.administered_at if last_log else None

        # Calculamos la siguiente dosis inmediata
        next_dose = calculate_next_dose_time(t, last_time)

        doses_today_str = []

        # Proyección de dosis para lo que queda del día
        temp_dose = next_dose
        while temp_dose:
            # Si ya pasó de hoy (mañana), paramos la proyección del día
            if timezone.localtime(temp_dose).date() > today:
                break

            time_str = timezone.localtime(temp_dose).strftime("%I:%M %p")

            # Marcador visual
            if temp_dose < now:
                doses_today_str.append(f"🔴 {time_str} (Atrasada)")
            else:
                doses_today_str.append(f"🟢 {time_str}")

            # Calculamos la siguiente teórica para el loop
            temp_dose = temp_dose + timedelta(hours=t.frequency_hours)
            # Validar fin de tratamiento
            if t.end_date and temp_dose > t.end_date:
                break

        if doses_today_str:
            schedule = "\n".join(doses_today_str)
            events.append(f"💊 **{t.medicine_name}:**\n{schedule}")
        elif next_dose:
            # Si no hay hoy, pero hay mañana
            next_str = timezone.localtime(next_dose).strftime("%d/%m %I:%M %p")
            events.append(f"💊 **{t.medicine_name}:**\nSiguiente: {next_str}")

    # 3. PRÓXIMAS CITAS (Lista de pendientes)
    future_appts = await sync_to_async(list)(
        Appointment.objects.filter(
            profile=profile, date__gte=now, is_completed=False
        ).order_by("date")[
            :5
        ]  # Limitamos a las próximas 5 para no saturar
    )

    if future_appts:
        appt_list = []
        for appt in future_appts:
            date_str = timezone.localtime(appt.date).strftime("%d/%m %I:%M %p")
            appt_list.append(f"🗓️ {date_str} - {appt.specialist}")

        events.append(f"👨‍⚕️ **Citas Pendientes:**\n" + "\n".join(appt_list))

    return events

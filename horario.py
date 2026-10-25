#!/usr/bin/env python3
"""Decide si toca buscar ahora, según la hora de España.

GitHub lanza este programa cada hora (y a veces con retraso o saltándose alguna).
Aquí se mira cuál fue la última hora programada que ya ha pasado y si la última
búsqueda es anterior a ella. Si lo es, falta una búsqueda y se hace ahora; así
nunca se pierde ninguna. Las ejecuciones a mano (botón "Run workflow") siempre tocan.

Horario: lunes a viernes 8:00 y 17:00; sábado y domingo 6, 10, 14, 18 y 22 h.
"""
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")
ENTRE_SEMANA = [8, 17]
FIN_DE_SEMANA = [6, 10, 14, 18, 22]
MARGEN = timedelta(minutes=20)   # una búsqueda hecha hasta 20 min antes de la hora cuenta


def ultima_programada(ahora):
    for h in range(0, 24 * 8):
        d = (ahora - timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
        horas = FIN_DE_SEMANA if d.weekday() >= 5 else ENTRE_SEMANA
        if d.hour in horas and d <= ahora:
            return d
    return None


def ultima_busqueda():
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos", "historial.json")
    try:
        with open(ruta, encoding="utf-8") as f:
            s = json.load(f).get("ultima")
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(MADRID) if s else None
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return None


ahora = datetime.now(MADRID)
manual = os.environ.get("EVENTO", "") == "workflow_dispatch"
tocaba = ultima_programada(ahora)
ultima = ultima_busqueda()
falta = tocaba is not None and (ultima is None or ultima < tocaba - MARGEN)
toca = manual or falta

print(f"Ahora: {ahora:%a %d/%m %H:%M} · Última programada: {tocaba:%a %d/%m %H:%M} · "
      f"Última hecha: {ultima:%a %d/%m %H:%M}" if ultima else f"Ahora: {ahora:%a %d/%m %H:%M} · sin búsquedas previas")
print("¿Toca buscar?", "sí (a mano)" if manual else ("sí, falta la de las %s" % f"{tocaba:%H:%M}" if falta else "no"))
with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a", encoding="utf-8") as f:
    f.write(f"toca={'si' if toca else 'no'}\n")

#!/usr/bin/env python3
"""Decide si esta ejecución programada toca, según la hora de España.

GitHub solo entiende la hora UTC, así que el horario se programa dos veces
(horario de invierno y de verano) y aquí se descarta la que no corresponde.
Ejecuciones a mano (botón "Run workflow") siempre tocan.
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

INVIERNO = {"0 7,16 * * 1-5", "0 5,9,13,17,21 * * 0,6"}   # España = UTC+1
VERANO = {"0 6,15 * * 1-5", "0 4,8,12,16,20 * * 0,6"}     # España = UTC+2

prog = os.environ.get("SCHEDULE", "").strip()
desfase = datetime.now(ZoneInfo("Europe/Madrid")).utcoffset().total_seconds() / 3600

if not prog:
    toca = True
elif prog in INVIERNO:
    toca = desfase == 1
elif prog in VERANO:
    toca = desfase == 2
else:
    toca = True

print(f"Programación: {prog or 'manual'} · España UTC+{desfase:g} · ¿toca? {'sí' if toca else 'no'}")
with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a", encoding="utf-8") as f:
    f.write(f"toca={'si' if toca else 'no'}\n")

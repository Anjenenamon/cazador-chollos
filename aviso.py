#!/usr/bin/env python3
"""Escribe el resumen de la última búsqueda (para el aviso por correo)."""
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

RAIZ = os.path.dirname(os.path.abspath(__file__))
PAGINA = "https://anjenenamon.github.io/cazador-chollos/"
MAX_CHOLLOS = 5


def eur(n):
    return f"{n:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


with open(os.path.join(RAIZ, "docs", "datos.json"), encoding="utf-8") as f:
    d = json.load(f)

cuando = datetime.fromisoformat(d["actualizado"].replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Madrid"))
lineas = [f"### Búsqueda del {cuando:%d/%m a las %H:%M} ✅", ""]
for b in d["busquedas"]:
    tope = b["precio_max"]
    items = [x for x in b["items"] if x["total"] <= tope]
    nuevos = [x for x in items if x.get("nuevo")]
    chollos_nuevos = sorted((x for x in nuevos if x.get("chollo")), key=lambda x: -(x.get("desc") or 0))
    lineas.append(f"**{b['nombre']}** (hasta {eur(tope)}): {len(items)} anuncios · "
                  f"{len(nuevos)} nuevos · {len(chollos_nuevos)} chollos nuevos")
    lineas.append("")
    if chollos_nuevos:
        lineas.append("Mejores chollos nuevos:")
        for x in chollos_nuevos[:MAX_CHOLLOS]:
            motivo = x["motivos"][0] if x.get("motivos") else ""
            lineas.append(f"- [{x['titulo']}]({x['url']}) — **{eur(x['total'])}** con envío"
                          f"{' e impuestos' if not x.get('ue') else ''} · {motivo}")
        lineas.append("")
    else:
        lineas.append("Esta vez no han aparecido chollos nuevos.")
        lineas.append("")
for a in d.get("avisos", []):
    lineas.append(f"⚠️ {a}")
lineas.append(f"[Abrir la página de chollos]({PAGINA})")
print("\n".join(lineas))

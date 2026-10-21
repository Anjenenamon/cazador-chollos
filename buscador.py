#!/usr/bin/env python3
"""Cazador de Chollos: busca anuncios en eBay y genera docs/datos.json para la página.

Solo usa la biblioteca estándar de Python. Necesita dos variables de entorno
(guardadas como "Secrets" en GitHub): EBAY_APP_ID y EBAY_CERT_ID.
"""
import base64
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(RAIZ, "busquedas.json")
HISTORIAL = os.path.join(RAIZ, "datos", "historial.json")
SALIDA = os.path.join(RAIZ, "docs", "datos.json")

API = "https://api.ebay.com"
UE = set("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split())
PAISES = {
    "ES": "España", "DE": "Alemania", "FR": "Francia", "IT": "Italia", "GB": "Reino Unido",
    "US": "Estados Unidos", "UA": "Ucrania", "RU": "Rusia", "BY": "Bielorrusia", "LT": "Lituania",
    "LV": "Letonia", "EE": "Estonia", "PL": "Polonia", "JP": "Japón", "CN": "China", "HK": "Hong Kong",
    "NL": "Países Bajos", "BE": "Bélgica", "AT": "Austria", "CH": "Suiza", "PT": "Portugal",
    "BG": "Bulgaria", "RO": "Rumanía", "CZ": "Chequia", "SK": "Eslovaquia", "HU": "Hungría",
    "GR": "Grecia", "HR": "Croacia", "SI": "Eslovenia", "IE": "Irlanda", "DK": "Dinamarca",
    "SE": "Suecia", "FI": "Finlandia", "NO": "Noruega", "CA": "Canadá", "AU": "Australia",
    "IL": "Israel", "TR": "Turquía", "TH": "Tailandia", "IN": "India", "SG": "Singapur",
    "MY": "Malasia", "TW": "Taiwán", "KR": "Corea del Sur", "MD": "Moldavia", "GE": "Georgia",
    "KZ": "Kazajistán", "RS": "Serbia", "BA": "Bosnia", "MK": "Macedonia del Norte", "AL": "Albania",
    "CY": "Chipre", "MT": "Malta", "LU": "Luxemburgo", "MX": "México", "BR": "Brasil", "AR": "Argentina",
}
DOMINIO = {"EBAY_ES": "ebay.es", "EBAY_DE": "ebay.de", "EBAY_FR": "ebay.fr", "EBAY_IT": "ebay.it",
           "EBAY_GB": "ebay.co.uk", "EBAY_US": "ebay.com"}
MONEDA = {"EBAY_GB": "GBP", "EBAY_US": "USD"}
TASAS_RESERVA = {"EUR": 1.0, "USD": 1.08, "GBP": 0.85}
GESTION_ADUANA = 5.0
ENVIO_SUPUESTO_UE = 10.0
ENVIO_SUPUESTO_FUERA = 20.0
UMBRAL_CHOLLO = 35          # % por debajo del habitual (Cómpralo ya)
UMBRAL_SUBASTA = 50         # subastas: más exigente, porque aún pueden subir
HORAS_SUBASTA = 3           # y solo si quedan pocas horas
MIN_REFERENCIAS = 8         # anuncios mínimos para calcular el precio habitual
PERCENTIL_CHOLLO = 10       # además debe estar entre el 10 % más barato de su marca
MARGEN_SALIDA = 1.25        # en la página se guardan anuncios hasta 1,25 × el precio máximo
DIAS_HISTORIAL = 60


def log(*a):
    print(*a, flush=True)


def ahora():
    return datetime.now(timezone.utc)


def iso(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def leer_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def http(url, cabeceras=None, datos=None, intentos=3):
    for n in range(intentos):
        req = urllib.request.Request(url, data=datos, headers=cabeceras or {})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode("utf-8", "replace")[:400]
            if e.code in (429, 500, 502, 503, 504) and n < intentos - 1:
                time.sleep(3 * (n + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {cuerpo}") from None
        except urllib.error.URLError as e:
            if n < intentos - 1:
                time.sleep(3 * (n + 1))
                continue
            raise RuntimeError(f"Sin conexión: {e.reason}") from None
        except (TimeoutError, ConnectionError, OSError, ValueError) as e:
            # eBay tarda en responder, corta la conexión o devuelve algo ilegible
            if n < intentos - 1:
                time.sleep(3 * (n + 1))
                continue
            raise RuntimeError(f"eBay no respondió bien: {type(e).__name__}") from None


# ---------- eBay ----------

def token(app_id, cert_id):
    cred = base64.b64encode(f"{app_id}:{cert_id}".encode()).decode()
    cuerpo = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }).encode()
    r = http(f"{API}/identity/v1/oauth2/token",
             {"Authorization": f"Basic {cred}", "Content-Type": "application/x-www-form-urlencoded"}, cuerpo)
    return r["access_token"]


def tasas_cambio():
    for url in ("https://api.frankfurter.dev/v1/latest?base=EUR&symbols=USD,GBP",
                "https://api.frankfurter.app/latest?from=EUR&to=USD,GBP"):
        try:
            r = http(url, {"User-Agent": "cazador-chollos"}, intentos=2)
            t = {"EUR": 1.0}
            t.update({k: float(v) for k, v in r["rates"].items()})
            log("Tipos de cambio:", t)
            return t
        except Exception as e:  # noqa: BLE001
            log("Aviso: no se pudo leer el cambio de moneda:", e)
    return dict(TASAS_RESERVA)


def buscar(tok, mercado, consulta, categoria, precio_tope, cfg, orden):
    moneda = MONEDA.get(mercado, "EUR")
    filtros = [
        f"price:[..{int(precio_tope)}]",
        f"priceCurrency:{moneda}",
        f"deliveryCountry:{cfg['pais_entrega']}",
        "buyingOptions:{FIXED_PRICE|AUCTION|BEST_OFFER}",
    ]
    params = {"q": consulta, "limit": "200", "filter": ",".join(filtros), "sort": orden}
    if categoria:
        params["category_ids"] = categoria
    ctx = f"contextualLocation=country={cfg['pais_entrega']},zip={cfg.get('codigo_postal', '')}"
    cab = {
        "Authorization": f"Bearer {tok}",
        "X-EBAY-C-MARKETPLACE-ID": mercado,
        "X-EBAY-C-ENDUSERCTX": urllib.parse.quote(ctx, safe="=,"),
        "Accept-Language": "es-ES",
    }
    url = f"{API}/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode(params)
    return http(url, cab).get("itemSummaries", []) or []


# ---------- Análisis ----------

def patron(palabras):
    partes = [re.escape(p.strip().lower()) for p in palabras if p.strip()]
    if not partes:
        return None
    return re.compile(r"(?<!\w)(" + "|".join(partes) + r")(?!\w)")


def a_euros(valor, moneda, tasas):
    if valor is None:
        return None
    return float(valor) / tasas.get(moneda, TASAS_RESERVA.get(moneda, 1.0))


def dinero(obj, tasas):
    if not obj or obj.get("value") is None:
        return None
    return a_euros(obj["value"], obj.get("currency", "EUR"), tasas)


DECADA = [
    (re.compile(r"(?<!\d)(19[2-9]\d)(?!\d)"), lambda m: int(m.group(1)) // 10 * 10),
    (re.compile(r"\b(?:años|anni|années|annees|years)\s*'?([2-9]0)\b"), lambda m: 1900 + int(m.group(1))),
    (re.compile(r"\b'?([2-9]0)\s*(?:s|er|'s)\b"), lambda m: 1900 + int(m.group(1))),
]
RUBIES = re.compile(r"\b(\d{2})\s*(?:jewels?|rubis|rubíes|rubies|rubini|steine|stones|kamney|камней|камня|j\b)")


def decada(t):
    for rx, f in DECADA:
        m = rx.search(t)
        if m:
            d = f(m)
            if 1920 <= d <= 2000:
                return d
    return None


def movimiento(t):
    if re.search(r"automat|self.?wind|selbstaufzug", t):
        return "Automático"
    if re.search(r"cuerda|hand.?wind|manual|handaufzug|remontage|carica manuale|manual wind", t):
        return "Cuerda manual"
    return "Mecánico"


def analizar(raw, mercado, b, pats, tasas, cfg):
    titulo = raw.get("title", "")
    t = " " + titulo.lower() + " "
    if pats["excluir"] and pats["excluir"].search(t):
        return None
    if pats.get("inicio") and pats["inicio"].match(titulo.lower().strip()):
        return None

    opciones = raw.get("buyingOptions", [])
    subasta = "AUCTION" in opciones
    precio = dinero(raw.get("currentBidPrice"), tasas) if subasta else None
    if precio is None:
        precio = dinero(raw.get("price"), tasas)
    if precio is None:
        return None

    loc = (raw.get("itemLocation") or {}).get("country", "") or ""
    ue = loc in UE
    envio, envio_est = None, False
    for op in raw.get("shippingOptions") or []:
        coste = dinero(op.get("shippingCost"), tasas)
        if coste is not None:
            envio = coste if envio is None else min(envio, coste)
    if envio is None:
        envio_est = True
        envio = ENVIO_SUPUESTO_UE if ue else ENVIO_SUPUESTO_FUERA

    base = precio + envio
    arancel = iva = gestion = 0.0
    if not ue:
        arancel = base * b.get("arancel", 0.0) if base > 150 else 0.0
        iva = (base + arancel) * 0.21
        gestion = GESTION_ADUANA
    total = base + arancel + iva + gestion

    marca = None
    for nombre, rx in pats["marcas"]:
        if rx.search(t):
            marca = nombre
            break
    lote = bool(pats["lote"] and pats["lote"].search(t))
    if lote:
        marca = "Varios (lote)"
    errata = None
    for mal, bien in b.get("erratas", {}).items():
        if re.search(r"(?<!\w)" + re.escape(mal) + r"(?!\w)", t):
            errata = (mal, bien)
            break

    mujer = bool(pats.get("mujer") and pats["mujer"].search(t))
    reparar = str(raw.get("conditionId", "")) == "7000" or bool(pats["reparar"] and pats["reparar"].search(t))

    m = RUBIES.search(t)
    img = (raw.get("image") or {}).get("imageUrl") or ""
    if not img:
        ths = raw.get("thumbnailImages") or []
        img = ths[0].get("imageUrl", "") if ths else ""

    return {
        "id": raw.get("itemId"),
        "titulo": titulo,
        "url": raw.get("itemWebUrl", ""),
        "foto": img,
        "marca": marca or "Otras",
        "mujer": mujer,
        "errata": errata,
        "lote": lote,
        "mercado": DOMINIO.get(mercado, mercado),
        "pais": loc,
        "pais_nombre": PAISES.get(loc, loc or "¿?"),
        "ue": ue,
        "precio": round(precio, 2),
        "envio": round(envio, 2),
        "envio_estimado": envio_est,
        "arancel": round(arancel, 2),
        "iva": round(iva, 2),
        "gestion": round(gestion, 2),
        "total": round(total, 2),
        "formato": "Subasta" if subasta else "Cómpralo ya",
        "ofertas": "BEST_OFFER" in opciones,
        "pujas": raw.get("bidCount", 0) if subasta else None,
        "fin": raw.get("itemEndDate"),
        "publicado": raw.get("itemCreationDate"),
        "estado": "Para reparar" if reparar else "Funciona",
        "decada": decada(t),
        "movimiento": movimiento(t),
        "rubies": int(m.group(1)) if m and 7 <= int(m.group(1)) <= 41 else None,
    }


def horas_hasta(fin_iso, ref):
    f = leer_iso(fin_iso)
    return (f - ref).total_seconds() / 3600 if f else None


def clave_ref(marca, mujer):
    return f"{marca} (mujer)" if mujer else marca


def evaluar(it, habitual, ref, barato=None):
    """Añade precio habitual, % de descuento, si es chollo y los motivos.

    habitual: mediana de precios de su marca. barato: precio por debajo del cual
    está el 10 % más barato de su marca.
    """
    motivos = []
    entre_baratos = barato is not None and it["total"] <= barato
    it["habitual"] = round(habitual, 2) if habitual else None
    it["desc"] = None
    if habitual:
        it["desc"] = round((1 - it["total"] / habitual) * 100)
    h = horas_hasta(it["fin"], ref)
    es_subasta = it["formato"] == "Subasta"
    # En una subasta el precio sube; solo la comparamos con el habitual si queda poco.
    if es_subasta:
        chollo = bool(entre_baratos and h is not None and h <= HORAS_SUBASTA
                      and it["desc"] is not None and it["desc"] >= UMBRAL_SUBASTA)
    else:
        chollo = bool(entre_baratos and it["desc"] is not None and it["desc"] >= UMBRAL_CHOLLO)
    if chollo:
        quien = f"{it['marca']} de mujer" if it["mujer"] else it["marca"]
        motivos.append(f"{it['desc']} % por debajo de lo habitual para {quien}")
    if es_subasta and h is not None and h <= 12 and (it["pujas"] or 0) <= 2:
        motivos.append(f"Subasta con {it['pujas'] or 0} puja{'s' if (it['pujas'] or 0) != 1 else ''} y termina en {max(1, round(h))} h")
    if it["errata"]:
        mal, bien = it["errata"]
        motivos.append(f"Marca mal escrita («{mal}»): pocos lo encuentran ({bien})")
    if it["lote"]:
        motivos.append("Lote con título genérico: puede esconder algo bueno")
    it["chollo"] = chollo
    it["motivos"] = motivos
    it.pop("errata", None)
    return it


# ---------- Principal ----------

def cargar_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return defecto


def guardar_json(ruta, datos, compacto=False):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        if compacto:
            json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(datos, f, ensure_ascii=False, indent=1)


def main():
    app_id = os.environ.get("EBAY_APP_ID", "").strip()
    cert_id = os.environ.get("EBAY_CERT_ID", "").strip()
    if not app_id or not cert_id:
        log("ERROR: faltan las claves EBAY_APP_ID y EBAY_CERT_ID (Settings → Secrets → Actions).")
        sys.exit(1)

    cfg = cargar_json(CONFIG, None)
    hist = cargar_json(HISTORIAL, {"ultima": None, "vistos": {}})
    ref = ahora()
    tasas = tasas_cambio()
    try:
        tok = token(app_id, cert_id)
    except Exception as e:  # noqa: BLE001
        log("ERROR: eBay no acepta las claves. Revisa EBAY_APP_ID y EBAY_CERT_ID.", e)
        sys.exit(1)

    hubo_anterior = bool(hist.get("ultima"))
    salida = {"actualizado": iso(ref), "anterior": hist.get("ultima"), "busquedas": [], "avisos": []}
    llamadas = errores = 0

    for b in cfg["busquedas"]:
        pats = {
            "excluir": patron(b.get("excluir", [])),
            "reparar": patron(b.get("palabras_reparar", [])),
            "lote": patron(b.get("palabras_lote", [])),
            "mujer": patron(b.get("palabras_mujer", [])),
            "inicio": patron(b.get("excluir_si_empieza", [])),
            "marcas": [(n, patron(alias)) for n, alias in b.get("marcas", {}).items()],
        }
        tope_eur = b["precio_max"] * 2  # guardamos hasta el doble para tener precios de referencia
        items = {}
        categoria = b.get("categoria")
        for mercado in cfg["mercados"]:
            moneda = MONEDA.get(mercado, "EUR")
            tope = tope_eur * tasas.get(moneda, 1.0)
            for consulta in b["consultas"]:
                for orden in ("newlyListed", "endingSoonest"):
                    llamadas += 1
                    try:
                        res = buscar(tok, mercado, consulta, categoria, tope, cfg, orden)
                    except RuntimeError as e:
                        if categoria and "categor" in str(e).lower():
                            try:
                                res = buscar(tok, mercado, consulta, None, tope, cfg, orden)
                            except RuntimeError as e2:
                                errores += 1
                                log(f"  Aviso {mercado} «{consulta}»: {e2}")
                                continue
                        else:
                            errores += 1
                            log(f"  Aviso {mercado} «{consulta}»: {e}")
                            continue
                    for raw in res:
                        iid = raw.get("itemId")
                        if not iid or iid in items:
                            continue
                        it = analizar(raw, mercado, b, pats, tasas, cfg)
                        if it:
                            items[iid] = it
            log(f"{b['id']} · {mercado}: {len(items)} anuncios acumulados")

        # Historial: cuándo vimos cada anuncio por primera vez y su precio (para el "habitual").
        vistos = hist.setdefault("vistos", {})
        for iid, it in items.items():
            v = vistos.get(iid)
            it["nuevo"] = hubo_anterior and v is None
            vistos[iid] = {
                "b": b["id"], "marca": clave_ref(it["marca"], it["mujer"]), "total": it["total"],
                "fijo": it["formato"] != "Subasta",
                "primera": v["primera"] if v else iso(ref), "visto": iso(ref),
            }

        # Precio habitual por marca: mediana de anuncios de precio fijo vistos (mín. 5).
        por_marca = {}
        for v in vistos.values():
            if v.get("b") == b["id"] and v.get("fijo") and v.get("marca") not in ("Otras", "Varios (lote)"):
                por_marca.setdefault(v["marca"], []).append(v["total"])
        habitual = {m: statistics.median(p) for m, p in por_marca.items() if len(p) >= MIN_REFERENCIAS}
        barato = {m: statistics.quantiles(p, n=100)[PERCENTIL_CHOLLO - 1]
                  for m, p in por_marca.items() if len(p) >= MIN_REFERENCIAS}

        tope_salida = b["precio_max"] * MARGEN_SALIDA
        lista = []
        for it in items.values():
            if it["total"] <= tope_salida:
                k = clave_ref(it["marca"], it["mujer"])
                lista.append(evaluar(it, habitual.get(k), ref, barato.get(k)))
        lista.sort(key=lambda x: (not x["chollo"], -(x["desc"] or -999)))
        salida["busquedas"].append({
            "id": b["id"], "nombre": b["nombre"], "precio_max": b["precio_max"],
            "items": lista,
            "referencias": {m: {"mediana": round(v, 2), "n": len(por_marca[m])} for m, v in habitual.items()},
        })
        log(f"{b['id']}: {len(lista)} anuncios, {sum(x['chollo'] for x in lista)} chollos, "
            f"{sum(x['nuevo'] for x in lista)} nuevos")

    # Limpiar historial viejo
    limite = ref - timedelta(days=DIAS_HISTORIAL)
    hist["vistos"] = {k: v for k, v in hist["vistos"].items() if (leer_iso(v.get("visto")) or ref) >= limite}
    hist["ultima"] = iso(ref)

    if errores and errores >= llamadas * 0.5:
        salida["avisos"].append(f"Muchas búsquedas fallaron ({errores} de {llamadas}). Los resultados pueden estar incompletos.")
    log(f"Llamadas a eBay: {llamadas}, errores: {errores}")
    if errores == llamadas:
        log("ERROR: todas las búsquedas fallaron; no se actualiza la página.")
        sys.exit(1)

    guardar_json(SALIDA, salida, compacto=True)
    guardar_json(HISTORIAL, hist, compacto=True)


if __name__ == "__main__":
    main()

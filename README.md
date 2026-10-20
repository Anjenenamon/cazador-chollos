# Cazador de Chollos

Buscador automático de chollos en eBay (todo el mundo, con precio final puesto en España).

- **La página:** se publica sola en GitHub Pages después de cada búsqueda.
- **Horario (hora de España):** lunes a viernes a las 8:00 y 17:00; sábado y domingo a las 6, 10, 14, 18 y 22 h.
- **Buscar ahora a mano:** pestaña *Actions* → *Buscar chollos* → botón *Run workflow*.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `busquedas.json` | Qué se busca: palabras, precio máximo, marcas, palabras a descartar. Cada bloque es una pestaña de la página. |
| `buscador.py` | Pide los anuncios a eBay, calcula el precio final y detecta chollos. |
| `horario.py` | Decide si toca buscar según la hora de España (invierno/verano). |
| `.github/workflows/buscar.yml` | El horario automático y la publicación de la página. |
| `docs/index.html` | La página web. |
| `docs/datos.json` | Resultados de la última búsqueda (lo escribe el buscador). |
| `datos/historial.json` | Anuncios ya vistos: sirve para marcar los NUEVOS y calcular el precio habitual. |

## Claves de eBay

Se guardan en *Settings → Secrets and variables → Actions* con los nombres `EBAY_APP_ID` y `EBAY_CERT_ID`. Nunca se escriben en el código.

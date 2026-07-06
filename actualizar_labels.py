"""Refresca network_labels.json desde Insight (requiere la cookie de sesion).

network_label y nickname solo existen en el backend de reportes de Insight, que
exige la cookie de sesion (no el X-User-Token). Este script la usa para bajar la
lista y regenerar network_labels.json. Correlo cuando cambien los labels (raro).

Como obtener la cookie:
  1. En https://insight.eero.com (ya logueado), F12 -> Network -> filtro "graphql".
  2. Recarga (F5), clic en cualquier peticion "graphql".
  3. Headers -> Request Headers -> copia el valor COMPLETO de "cookie".
  4. Pegalo en un archivo llamado "cookie.txt" junto a este script.
  5. Ejecuta:  python actualizar_labels.py

La cookie expira; cuando el script falle con 401, consigue una cookie nueva igual.
"""
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import json
import os

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE, "cookie.txt")
OUT = os.path.join(BASE, "network_labels.json")
ORG_ID = "181421"

QUERY = (
    "query GetNetworkListByOrg($organizationId: IntOrString, "
    "$columns: [TableColumnInput!]!, $pageSize: Int, $offset: Int, $locale: String) "
    "{ organization(id: $organizationId) { networks(columns: $columns, offset: $offset, "
    "pageSize: $pageSize, locale: $locale) { data pagination { totalCount: totalHits "
    "__typename } __typename } __typename } }"
)

COLUMNS = [
    {"is_active": True, "name": "Network ID", "field": "network_id",
     "data_type": "NETWORK_LINK", "filters": [], "sort": None},
    {"is_active": True, "name": "Network Label", "field": "network_label",
     "data_type": "STRING", "filters": [], "sort": None},
    {"is_active": True, "name": "Nickname", "field": "nickname",
     "data_type": "STRING", "filters": [], "sort": None},
]


def fetch(cookie, offset, page_size=200):
    body = {
        "operationName": "GetNetworkListByOrg",
        "variables": {
            "pageSize": page_size, "organizationId": ORG_ID,
            "offset": offset, "columns": COLUMNS, "locale": "en-US",
        },
        "query": QUERY,
    }
    headers = {
        "content-type": "application/json",
        "apollo-require-preflight": "true",
        "origin": "https://insight.eero.com",
        "referer": "https://insight.eero.com/",
        "cookie": cookie,
    }
    r = requests.post("https://api.insight.eero.com/graphql", json=body,
                      headers=headers, timeout=30)
    r.raise_for_status()
    j = r.json()
    if j.get("errors"):
        raise SystemExit("Error de la API (cookie vencida?): "
                         + json.dumps(j["errors"])[:400])
    return j["data"]["organization"]["networks"]


def refresh(cookie):
    """Baja la lista con la cookie y regenera network_labels.json.

    Devuelve un texto resumen. Lanza SystemExit si la cookie es invalida/vencida.
    """
    rows, offset = [], 0
    while True:
        page = fetch(cookie, offset)
        data = page["data"]
        rows.extend(data)
        total = page["pagination"]["totalCount"]
        offset += len(data)
        if not data or offset >= total:
            break

    mapa = {
        str(n["network_id"]): {
            "label": n.get("network_label", "") or "",
            "nickname": n.get("nickname", "") or "",
        }
        for n in rows
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, indent=2)

    con = sum(1 for v in mapa.values() if v["label"] or v["nickname"])
    return f"{len(mapa)} redes actualizadas ({con} con label/nickname)."


def main():
    if not os.path.exists(COOKIE_FILE):
        raise SystemExit(
            f"Falta {COOKIE_FILE}. Pega ahi la cookie de Insight "
            "(ver instrucciones al inicio de este archivo)."
        )
    cookie = open(COOKIE_FILE, encoding="utf-8").read().strip()
    print("OK: " + refresh(cookie))


if __name__ == "__main__":
    main()

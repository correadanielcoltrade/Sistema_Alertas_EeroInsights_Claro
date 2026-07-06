"""Cliente HTTP para la API de eero (endpoints de interrupciones de red)."""
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("eero")

BASE = "https://api-user.e2ro.com"


class EeroAuthError(Exception):
    """Token de eero invalido o expirado (HTTP 401/403)."""


class EeroClient:
    def __init__(self, admin_token, org_id="self"):
        self.org = org_id
        self.s = requests.Session()
        self.s.headers.update({"X-User-Token": admin_token})
        # Reintentos automaticos ante fallos temporales del servidor de eero
        # (500/502/503/504) y errores de conexion, con backoff exponencial.
        retry = Retry(
            total=3,
            backoff_factor=1.5,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        self.s.mount("https://", HTTPAdapter(max_retries=retry))

    def _get(self, path, params=None):
        url = BASE + path
        r = self.s.get(url, params=params, timeout=30)
        if r.status_code in (401, 403):
            raise EeroAuthError(f"HTTP {r.status_code} en {path}")
        r.raise_for_status()
        return r.json().get("data", {})

    def networks_with_outages(self, limit=200):
        """Redes con interrupciones recientes/activas.

        Devuelve la lista 'networks'. Cada item trae:
        network_id, duration, geo_ip, start_time, end_time.
        end_time == None  -> la caida sigue ACTIVA.
        """
        data = self._get(
            f"/2.2/organizations/{self.org}/network_outages/networks",
            params={"sortBy": "start_time", "desc": "true", "limit": limit},
        )
        return data.get("networks", [])

    def outage_detail(self, network_id, start):
        """Detalle de interrupciones de una red (incluye 'reason')."""
        data = self._get(
            f"/2.2/organizations/{self.org}/network_outages/networks/{network_id}",
            params={"start": start},
        )
        return data.get("outages", [])

    def network_info(self, network_id):
        """Info de la red (nombre, etc.). Best-effort: si falla, devuelve {}."""
        try:
            return self._get(f"/2.2/networks/{network_id}")
        except (requests.HTTPError, EeroAuthError):
            return {}

    # ---------- Redes no saludables (tiempo real) ----------

    def unhealthy_networks(self, limit=50):
        """Redes 'unhealthy' en tiempo real (criticas y no criticas).

        Cada item trae: network_id, network_type, highest_severity
        (CRITICAL / NON_CRITICAL), alerts (lista), count, last_occurrence, is_deleted.
        Nota: el endpoint acepta como maximo limit=50.
        """
        data = self._get(
            f"/2.2/organizations/{self.org}/unhealthy_networks/impacted_networks",
            params={"limit": limit},
        )
        networks = data.get("networks", [])
        if len(networks) >= limit:
            log.warning(
                "Se alcanzo el limite de %d redes unhealthy; podria haber mas sin listar.",
                limit,
            )
        return networks


def parse_geo_ip(geo_ip_str):
    """El campo geo_ip viene como string JSON. Lo convierte a dict de forma segura."""
    if not geo_ip_str:
        return {}
    try:
        return json.loads(geo_ip_str)
    except (json.JSONDecodeError, TypeError):
        return {}

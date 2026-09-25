"""The shared skysources HTTP client, plus per-host politeness for the hosts this package adds."""

from __future__ import annotations

from skysources.http import HOST_MIN_INTERVAL, CachedClient, UpstreamError, get_client

# Seconds between requests to one host. TNS asks for gentle use of its public search.
HOST_MIN_INTERVAL.setdefault("www.wis-tns.org", 5.0)
HOST_MIN_INTERVAL.setdefault("gcn.nasa.gov", 1.0)
HOST_MIN_INTERVAL.setdefault("ssd.jpl.nasa.gov", 1.0)
HOST_MIN_INTERVAL.setdefault("ssd-api.jpl.nasa.gov", 1.0)
HOST_MIN_INTERVAL.setdefault("api.alerce.online", 0.5)
HOST_MIN_INTERVAL.setdefault("ssp.imcce.fr", 1.0)

FRESH = 900.0  # 15 min: feeds that change during the day
DAY = 86400.0
FOREVER = 30 * DAY  # immutable documents (a published GCN circular, a sky map file)


def client() -> CachedClient:
    return get_client()


__all__ = ["DAY", "FOREVER", "FRESH", "UpstreamError", "client"]

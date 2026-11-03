"""
Live External Grid API Ingestion Service for EV-ChargeAI.

Fetches real-time grid carbon intensity data from the UK Carbon Intensity API
(api.carbonintensity.org.uk) — completely free, no API key required.

Maps carbon intensity index to IEEE 33-bus load scale factors:
  low        → 0.65  (off-peak valley)
  moderate   → 0.80  (standard daytime)
  high       → 0.95  (near-peak demand)
  very high  → 1.15  (grid stress / peak)

Falls back gracefully to stochastic diurnal model on any network/API error.
"""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger("EV-ChargeAI.LiveAPI")

# UK Carbon Intensity API — free, public, no authentication required
_CARBON_INTENSITY_URL = "https://api.carbonintensity.org.uk/intensity"

# Intensity index → load scale factor mapping
_INTENSITY_MAP = {
    "low":       0.65,
    "moderate":  0.80,
    "high":      0.95,
    "very high": 1.15,
}


class LiveGridAPIService:
    """
    Async background service that periodically fetches grid demand/intensity
    from a real public API and exposes a load-factor override for the simulator.
    """

    def __init__(self, fetch_interval_seconds: float = 60.0):
        self.fetch_interval_seconds: float = fetch_interval_seconds

        # Shared state (read by main.py / simulator integration)
        self.load_factor_override: Optional[float] = None
        self.data_source: str = "STOCHASTIC_MODEL"
        self.is_live: bool = False
        self.last_fetch_time: float = 0.0
        self.last_intensity_index: Optional[str] = None
        self.last_intensity_actual: Optional[int] = None

        self._lock = asyncio.Lock()
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def background_poll_loop(self) -> None:
        """
        Long-running asyncio task: poll the Carbon Intensity API every
        `fetch_interval_seconds` seconds, update the load_factor_override,
        and fall back silently on any error.
        """
        self._running = True
        logger.info("[LiveAPI] Background poll loop started (interval=%ds)", int(self.fetch_interval_seconds))

        # Immediate first fetch so data is available as soon as the server starts
        await self.fetch_and_update()

        while self._running:
            try:
                await asyncio.sleep(self.fetch_interval_seconds)
                await self.fetch_and_update()
            except asyncio.CancelledError:
                logger.info("[LiveAPI] Poll loop cancelled — shutting down.")
                self._running = False
                break
            except Exception as exc:
                # Any unexpected error → log and continue loop (never crash)
                logger.warning("[LiveAPI] Unexpected error in poll loop: %s", exc)
                await asyncio.sleep(self.fetch_interval_seconds)

    async def fetch_and_update(self) -> None:
        """
        Fetch carbon intensity from the UK API and update the load_factor_override.
        On any failure (network, parse, rate-limit) the override is cleared so the
        simulator seamlessly reverts to the stochastic diurnal model.
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    _CARBON_INTENSITY_URL,
                    headers={"Accept": "application/json"},
                )

            if response.status_code != 200:
                raise ValueError(f"HTTP {response.status_code} from Carbon Intensity API")

            body = response.json()
            data_list = body.get("data", [])
            if not data_list:
                raise ValueError("Empty data array from Carbon Intensity API")

            intensity_block = data_list[0].get("intensity", {})
            index = intensity_block.get("index", "").lower().strip()
            actual = intensity_block.get("actual") or intensity_block.get("forecast")

            if index not in _INTENSITY_MAP:
                raise ValueError(f"Unknown intensity index: '{index}'")

            load_factor = _INTENSITY_MAP[index]

            async with self._lock:
                self.load_factor_override = load_factor
                self.data_source = "LIVE_EXTERNAL_API"
                self.is_live = True
                self.last_fetch_time = time.time()
                self.last_intensity_index = index
                self.last_intensity_actual = actual

            logger.info(
                "[LiveAPI] ✓ Fetched — index='%s' actual=%s gCO2/kWh → load_factor=%.2f",
                index, actual, load_factor,
            )

        except ImportError:
            logger.warning("[LiveAPI] httpx not installed — running in stochastic fallback mode.")
            await self._set_fallback("httpx_missing")

        except Exception as exc:
            logger.warning("[LiveAPI] Fetch failed (%s) — falling back to stochastic model.", exc)
            await self._set_fallback(str(exc))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _set_fallback(self, reason: str) -> None:
        """Switch data source to stochastic fallback without blocking the sim."""
        async with self._lock:
            self.load_factor_override = None
            self.data_source = "STOCHASTIC_MODEL"
            self.is_live = False

    def get_status(self) -> dict:
        """Return a JSON-serialisable snapshot of the service state."""
        return {
            "source": self.data_source,
            "is_live": self.is_live,
            "load_factor_override": self.load_factor_override,
            "last_fetch_time": self.last_fetch_time,
            "last_intensity_index": self.last_intensity_index,
            "last_intensity_actual_gco2_kwh": self.last_intensity_actual,
            "fetch_interval_seconds": self.fetch_interval_seconds,
        }


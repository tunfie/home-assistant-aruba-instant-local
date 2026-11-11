"""One local poll shared by all entities."""
from datetime import timedelta
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import ArubaAuthError, ArubaClient, ArubaError
from .const import CONF_AP_ADDRESS, CONF_SCAN_INTERVAL, CONF_TLS_NAME, DEFAULT_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ArubaCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        data = entry.data
        # SSL context creation reads CA files; construct inside executor in setup.
        self.client = None
        self.entry = entry
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(seconds=entry.options.get(
                             CONF_SCAN_INTERVAL, data.get(CONF_SCAN_INTERVAL, DEFAULT_INTERVAL))),
                         always_update=False)

    async def _async_setup(self):
        data = self.entry.data
        self.client = await self.hass.async_add_executor_job(
            ArubaClient, data[CONF_HOST], data[CONF_PORT], data[CONF_TLS_NAME],
            data[CONF_AP_ADDRESS], data[CONF_USERNAME], data[CONF_PASSWORD])

    async def _async_update_data(self) -> dict:
        try:
            return await self.hass.async_add_executor_job(self.client.read)
        except ArubaAuthError as err:
            raise ConfigEntryAuthFailed("Aruba authentication rejected") from err
        except ArubaError as err:
            raise UpdateFailed(str(err)) from err

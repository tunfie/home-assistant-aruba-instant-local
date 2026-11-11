"""Native firmware activity and Wi-Fi profile states."""
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import callback
from .entity import ArubaEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities([ArubaUpgradeSensor(coordinator)])
    seen = set()

    @callback
    def discover():
        entities = []
        for row in coordinator.data["ssids"]:
            key = row["profile"] or row["name"]
            if key and key not in seen:
                seen.add(key)
                entities.append(ArubaSsidSensor(coordinator, key))
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class ArubaUpgradeSensor(ArubaEntity, BinarySensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator, "upgrade", "Firmware upgrade in progress")

    @property
    def is_on(self):
        return self.coordinator.data["upgrade_in_progress"]


class ArubaSsidSensor(ArubaEntity, BinarySensorEntity):
    def __init__(self, coordinator, profile):
        super().__init__(coordinator, "ssid_" + profile, "Wi-Fi " + profile)
        self._profile = profile

    def _row(self):
        return next((r for r in self.coordinator.data["ssids"]
                     if (r["profile"] or r["name"]) == self._profile), None)

    @property
    def available(self):
        return super().available and self._row() is not None

    @property
    def is_on(self):
        row = self._row()
        return bool(row and row["enabled"] and row["active"])

    @property
    def extra_state_attributes(self):
        return self._row() or {}

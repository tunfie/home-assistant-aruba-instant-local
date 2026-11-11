"""Network and opt-in client sensors."""
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import callback
from .entity import ArubaEntity

KEYS = {"aps": "Access points", "ssids": "Wi-Fi networks", "clients": "Connected clients"}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities([ArubaCountSensor(coordinator, key, name) for key, name in KEYS.items()]
                       + [ArubaFirmwareSensor(coordinator)])
    seen = set()

    @callback
    def discover():
        fresh = []
        for row in coordinator.data["clients"]:
            mac = row["mac"]
            if mac and mac not in seen:
                seen.add(mac)
                fresh.append(ArubaClientSignalSensor(coordinator, mac))
        if fresh:
            async_add_entities(fresh)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class ArubaCountSensor(ArubaEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, key, name)
        self._key = key

    @property
    def native_value(self):
        return len(self.coordinator.data[self._key])

    @property
    def extra_state_attributes(self):
        if self._key == "clients":
            return {}
        return {"networks" if self._key == "ssids" else "access_points":
                self.coordinator.data[self._key]}


class ArubaFirmwareSensor(ArubaEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator, "firmware", "Installed firmware")

    @property
    def native_value(self):
        return self.coordinator.data["firmware"]


class ArubaClientSignalSensor(ArubaEntity, SensorEntity):
    """Disabled by default to avoid recording visitors and rotating MACs."""
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:wifi"

    def __init__(self, coordinator, mac):
        super().__init__(coordinator, "signal_" + mac, "Client " + mac + " signal")
        self._mac = mac

    def _row(self):
        return next((r for r in self.coordinator.data["clients"] if r["mac"] == self._mac), None)

    @property
    def available(self):
        return super().available and self._row() is not None

    @property
    def native_value(self):
        row = self._row()
        return row["signal"] if row else None

    @property
    def extra_state_attributes(self):
        return self._row() or {}

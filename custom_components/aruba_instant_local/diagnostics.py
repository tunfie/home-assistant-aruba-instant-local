"""Diagnostics exclude credentials, addresses, SSIDs and client identifiers."""


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    return {
        "version": "0.1.0-beta.1",
        "available": coordinator.last_update_success,
        "ap_count": len(data.get("aps", [])),
        "ssid_count": len(data.get("ssids", [])),
        "client_count": len(data.get("clients", [])),
        "firmware": data.get("firmware"),
        "upgrade_in_progress": data.get("upgrade_in_progress"),
    }

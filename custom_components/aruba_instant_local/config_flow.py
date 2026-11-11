"""UI setup, options and reauthentication without shell commands."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, selector
from .api import ArubaApiDisabled, ArubaAuthError, ArubaClient, ArubaError, validate_host
from .const import CONF_AP_ADDRESS, CONF_SCAN_INTERVAL, CONF_TLS_NAME, DEFAULT_INTERVAL, DEFAULT_PORT, DOMAIN


def schema(data=None):
    data = data or {}
    return vol.Schema({
        vol.Required(CONF_HOST, default=data.get(CONF_HOST, "")): str,
        vol.Required(CONF_PORT, default=data.get(CONF_PORT, DEFAULT_PORT)): cv.port,
        vol.Required(CONF_TLS_NAME, default=data.get(CONF_TLS_NAME, "")): str,
        vol.Required(CONF_AP_ADDRESS, default=data.get(CONF_AP_ADDRESS, "")): str,
        vol.Required(CONF_USERNAME, default=data.get(CONF_USERNAME, "")): str,
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        vol.Required(CONF_SCAN_INTERVAL, default=data.get(CONF_SCAN_INTERVAL, DEFAULT_INTERVAL)):
            vol.All(vol.Coerce(int), vol.Range(min=30, max=600)),
    })


async def validate(hass, data):
    data = dict(data)
    data[CONF_HOST] = validate_host(data[CONF_HOST])
    data[CONF_TLS_NAME] = validate_host(data[CONF_TLS_NAME] or data[CONF_HOST])
    data[CONF_AP_ADDRESS] = validate_host(data[CONF_AP_ADDRESS] or data[CONF_HOST])
    if not data[CONF_USERNAME].strip() or not data[CONF_PASSWORD]:
        raise ValueError("Credentials required")
    client = await hass.async_add_executor_job(
        ArubaClient, data[CONF_HOST], data[CONF_PORT], data[CONF_TLS_NAME],
        data[CONF_AP_ADDRESS], data[CONF_USERNAME], data[CONF_PASSWORD])
    info = await hass.async_add_executor_job(client.read)
    return data, info


class ArubaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                data, info = await validate(self.hass, user_input)
            except ArubaApiDisabled:
                errors["base"] = "api_disabled"
            except ArubaAuthError:
                errors["base"] = "invalid_auth"
            except ArubaError:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "invalid_input"
            else:
                if info["serial"]:
                    await self.async_set_unique_id(info["serial"])
                    self._abort_if_unique_id_configured()
                self._async_abort_entries_match({CONF_HOST: data[CONF_HOST], CONF_PORT: data[CONF_PORT]})
                return self.async_create_entry(title="Aruba Instant", data=data)
        return self.async_show_form(step_id="user", data_schema=schema(user_input), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            try:
                data, info = await validate(self.hass, {**entry.data, **user_input})
            except ArubaApiDisabled:
                errors["base"] = "api_disabled"
            except ArubaAuthError:
                errors["base"] = "invalid_auth"
            except ArubaError:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "invalid_input"
            else:
                if entry.unique_id and info["serial"] != entry.unique_id:
                    return self.async_abort(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=data)
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema(entry.data), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ArubaOptionsFlow()


class ArubaOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_SCAN_INTERVAL, default=self.config_entry.options.get(
                CONF_SCAN_INTERVAL, self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_INTERVAL))):
                vol.All(vol.Coerce(int), vol.Range(min=30, max=600)),
        }))

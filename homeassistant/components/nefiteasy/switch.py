"""Support for Bosch home thermostats."""

import logging

from homeassistant.components.switch import SwitchEntity

from .const import CONF_SWITCHES, DOMAIN, SWITCH_TYPES
from .nefit_entity import NefitEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Switch setup for nefit easy."""
    entities = []
    for device in hass.data[DOMAIN]["devices"]:
        config = device["config"]

        for key in config[CONF_SWITCHES]:
            typeconf = SWITCH_TYPES[key]
            if key == "hot_water":
                entities.append(NefitHotWater(device, key, typeconf))
            elif key == "lockui":
                entities.append(NefitSwitchTrueFalse(device, key, typeconf))
            elif key == "weather_dependent":
                entities.append(NefitWeatherDependent(device, key, typeconf))
            elif key == "home_entrance_detection":
                await setup_home_entrance_detection(entities, device, key, typeconf)
            else:
                entities.append(NefitSwitch(device, key, typeconf))

    async_add_entities(entities, True)

    _LOGGER.debug("switch: async_setup_platform done")


async def setup_home_entrance_detection(entities, device, basekey, basetypeconf):
    """Home entrance detection setup."""
    for i in range(0, 10):
        userprofile_id = f"userprofile{i}"
        endpoint = f"/ecus/rrc/homeentrancedetection/{userprofile_id}/"
        is_active = await device["client"].get_value(
            userprofile_id, endpoint + "active"
        )
        _LOGGER.debug("hed switch: is_active: %s", is_active)
        if is_active == "on":
            name = await device["client"].get_value(userprofile_id, endpoint + "name")
            typeconf = {}
            typeconf["name"] = basetypeconf["name"].format(name)
            typeconf["url"] = endpoint + "detected"
            typeconf["icon"] = basetypeconf["icon"]
            entities.append(
                NefitSwitch(device, f"{basekey}_{userprofile_id}", typeconf)
            )


class NefitSwitch(NefitEntity, SwitchEntity):
    """Representation of a NefitSwitch entity."""

    @property
    def is_on(self):
        """Get whether the switch is in on state."""
        return self._client.data[self._key] == "on"

    @property
    def assumed_state(self) -> bool:
        """Return true if we do optimistic updates."""
        return False

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the entity on."""
        self._client.nefit.put_value(self.get_endpoint(), "on")

        _LOGGER.debug(
            "Switch Nefit %s ON, endpoint=%s.", self._key, self.get_endpoint()
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        self._client.nefit.put_value(self.get_endpoint(), "off")

        _LOGGER.debug(
            "Switch Nefit %s OFF, endpoint=%s.", self._key, self.get_endpoint()
        )


class NefitHotWater(NefitSwitch):
    """Class for nefit hot water entity."""

    def __init__(self, device, key, typeconf):
        """Initialize the switch."""
        super().__init__(device, key, typeconf)

        self._client.keys["/dhwCircuits/dhwA/dhwOperationClockMode"] = self._key
        self._client.keys["/dhwCircuits/dhwA/dhwOperationManualMode"] = self._key

    def get_endpoint(self):
        """Get end point."""
        endpoint = (
            "dhwOperationClockMode"
            if self._client.data.get("user_mode") == "clock"
            else "dhwOperationManualMode"
        )
        return "/dhwCircuits/dhwA/" + endpoint


class NefitWeatherDependent(NefitSwitch):
    """Class for nefit weather dependent entity."""

    @property
    def is_on(self):
        """Get whether the switch is in on state."""
        return self._client.data[self._key] == "weather"

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the entity on."""
        self._client.nefit.put_value(self.get_endpoint(), "weather")

        _LOGGER.debug("Switch weather dependent ON, endpoint=%s.", self.get_endpoint())

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        self._client.nefit.put_value(self.get_endpoint(), "room")

        _LOGGER.debug("Switch weather dependent OFF, endpoint=%s.", self.get_endpoint())


class NefitSwitchTrueFalse(NefitEntity, SwitchEntity):
    """Class for nefit true/false entity."""

    @property
    def is_on(self):
        """Get whether the switch is in on state."""
        return self._client.data[self._key] == "true"

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the entity on."""
        self._client.nefit.put_value(self.get_endpoint(), "true")

        _LOGGER.debug(
            "Switch Nefit %s ON, endpoint=%s.", self._key, self.get_endpoint()
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        self._client.nefit.put_value(self.get_endpoint(), "false")

        _LOGGER.debug(
            "Switch Nefit %s OFF, endpoint=%s.", self._key, self.get_endpoint()
        )

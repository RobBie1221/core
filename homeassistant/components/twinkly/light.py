"""The Twinkly light component."""

import asyncio
import logging
from typing import Any, Dict, Optional

from aiohttp import ClientError

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_WHITE_VALUE,
    ATTR_XY_COLOR,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_WHITE_VALUE,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType
import homeassistant.util.color as color_util

from .const import (
    ATTR_HOST,
    CONF_ENTRY_HOST,
    CONF_ENTRY_ID,
    CONF_ENTRY_MODEL,
    CONF_ENTRY_NAME,
    DEV_MODEL,
    DEV_NAME,
    DOMAIN,
    HIDDEN_DEV_VALUES,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistantType, config_entry: ConfigEntry, async_add_entities
) -> None:
    """Setups an entity from a config entry (UI config flow)."""

    entity = TwinklyLight(config_entry, hass)

    async_add_entities([entity], update_before_add=True)


class TwinklyLight(LightEntity):
    """Implementation of the light for the Twinkly service."""

    def __init__(
        self,
        conf: ConfigEntry,
        hass: HomeAssistantType,
    ):
        """Initialize a TwinklyLight entity."""
        self._id = conf.data[CONF_ENTRY_ID]
        self._hass = hass
        self._conf = conf
        self._hs = None
        self._white = 0
        self._rgb = None

        # Those are saved in the config entry in order to have meaningful values even
        # if the device is currently offline.
        # They are expected to be updated using the device_info.
        self.__name = conf.data[CONF_ENTRY_NAME]
        self.__model = conf.data[CONF_ENTRY_MODEL]

        self._client = hass.data.get(DOMAIN, {}).get(self._id)
        if self._client is None:
            raise ValueError(f"Client for {self._id} has not been configured.")

        # Set default state before any update
        self._is_on = False
        self._brightness = 0
        self._is_available = False
        self._attributes = {ATTR_HOST: self._client.host}

    @property
    def supported_features(self):
        """Get the features supported by this entity."""
        return SUPPORT_BRIGHTNESS | SUPPORT_COLOR | SUPPORT_WHITE_VALUE

    @property
    def should_poll(self) -> bool:
        """Get a boolean which indicates if this entity should be polled."""
        return True

    @property
    def available(self) -> bool:
        """Get a boolean which indicates if this entity is currently available."""
        return self._is_available

    @property
    def unique_id(self) -> Optional[str]:
        """Id of the device."""
        return self._id

    @property
    def name(self) -> str:
        """Name of the device."""
        return self.__name if self.__name else "Twinkly light"

    @property
    def model(self) -> str:
        """Name of the device."""
        return self.__model

    @property
    def icon(self) -> str:
        """Icon of the device."""
        return "mdi:string-lights"

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        """Get device specific attributes."""
        return (
            {
                "identifiers": {(DOMAIN, self._id)},
                "name": self.name,
                "manufacturer": "LEDWORKS",
                "model": self.model,
            }
            if self._id
            else None  # device_info is available only for entities configured from the UI
        )

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._is_on

    @property
    def brightness(self) -> Optional[int]:
        """Return the brightness of the light."""
        return self._brightness

    @property
    def hs_color(self):
        """Return the hs color."""
        return self._hs

    @property
    def white_value(self):
        """Return the white value of this light between 0..255."""
        return self._white

    @property
    def state_attributes(self) -> dict:
        """Return device specific state attributes."""

        attributes = self._attributes

        # Make sure to update any normalized property
        attributes[ATTR_HOST] = self._client.host
        attributes[ATTR_BRIGHTNESS] = self._brightness

        if self.hs_color:
            hs_color = self.hs_color
            attributes[ATTR_HS_COLOR] = (round(hs_color[0], 3), round(hs_color[1], 3))
            attributes[ATTR_RGB_COLOR] = color_util.color_hs_to_RGB(*hs_color)
            attributes[ATTR_XY_COLOR] = color_util.color_hs_to_xy(*hs_color)

        attributes[ATTR_WHITE_VALUE] = self.white_value

        return attributes

    async def async_turn_on(self, **kwargs) -> None:
        """Turn device on."""
        if ATTR_BRIGHTNESS in kwargs:
            brightness = int(int(kwargs[ATTR_BRIGHTNESS]) / 2.55)

            # If brightness is 0, the twinkly will only "disable" the brightness,
            # which means that it will be 100%.
            if brightness == 0:
                await self._client.set_is_on(False)
                return

            await self._client.set_brightness(brightness)

        rgbw = None

        if ATTR_WHITE_VALUE in kwargs:
            white = kwargs[ATTR_WHITE_VALUE]
        elif ATTR_HS_COLOR in kwargs:
            self._hs = kwargs[ATTR_HS_COLOR]
            if ATTR_WHITE_VALUE not in kwargs:
                white = self._white

        if (
            ATTR_WHITE_VALUE in kwargs or ATTR_HS_COLOR in kwargs
        ) and self._hs is not None:
            rgbw = "#"
            for colorval in color_util.color_hs_to_RGB(*self._hs):
                rgbw += format(colorval, "02x")

            r = int(rgbw[1:3], 16)
            g = int(rgbw[3:5], 16)
            b = int(rgbw[5:7], 16)

            if r == 255 and g == 255 and b == 255:
                r = 0
                g = 0
                b = 0

                if ATTR_HS_COLOR in kwargs:
                    if self._white == 0:
                        white = 255
                    else:
                        white = self._white
            elif ATTR_WHITE_VALUE not in kwargs:
                # white LED must be off in order for color to work
                if self._rgb == (0, 0, 0) and (r, g, b) != (0, 0, 0):
                    white = 0

            self._white = white
            self._rgb = (r, g, b)

            w = self._white

            await self._client.set_static_colour((w, r, g, b))

        if not kwargs:
            await self._client.set_is_on(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn device off."""
        await self._client.set_is_on(False)

    async def async_update(self) -> None:
        """Asynchronously updates the device properties."""
        _LOGGER.info("Updating '%s'", self._client.host)

        try:
            self._is_on = await self._client.get_is_on()

            self._brightness = (
                int(round((await self._client.get_brightness()) * 2.55))
                if self._is_on
                else 0
            )

            device_info = await self._client.get_device_info()

            if (
                DEV_NAME in device_info
                and DEV_MODEL in device_info
                and (
                    device_info[DEV_NAME] != self.__name
                    or device_info[DEV_MODEL] != self.__model
                )
            ):
                self.__name = device_info[DEV_NAME]
                self.__model = device_info[DEV_MODEL]

                if self._conf is not None:
                    # If the name has changed, persist it in conf entry,
                    # so we will be able to restore this new name if hass is started while the LED string is offline.
                    self._hass.config_entries.async_update_entry(
                        self._conf,
                        data={
                            CONF_ENTRY_HOST: self._client.host,  # this cannot change
                            CONF_ENTRY_ID: self._id,  # this cannot change
                            CONF_ENTRY_NAME: self.__name,
                            CONF_ENTRY_MODEL: self.__model,
                        },
                    )

            for key, value in device_info.items():
                if key not in HIDDEN_DEV_VALUES:
                    self._attributes[key] = value

            if not self._is_available:
                _LOGGER.info("Twinkly '%s' is now available", self._client.host)

            # We don't use the echo API to track the availability since we already have to pull
            # the device to get its state.
            self._is_available = True
        except (asyncio.TimeoutError, ClientError):
            # We log this as "info" as it's pretty common that the christmas light are not reachable in july
            if self._is_available:
                _LOGGER.info(
                    "Twinkly '%s' is not reachable (client error)", self._client.host
                )
            self._is_available = False

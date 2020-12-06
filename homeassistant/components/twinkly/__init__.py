"""The twinkly component."""

from typing import Any, Dict, Union

from aiohttp import ClientResponseError, ClientSession
import twinkly_client

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import HomeAssistantType

from .const import CONF_ENTRY_HOST, CONF_ENTRY_ID, DOMAIN


async def async_setup(hass: HomeAssistantType, config: dict):
    """Set up the twinkly integration."""

    return True


async def async_setup_entry(hass: HomeAssistantType, config_entry: ConfigEntry):
    """Set up entries from config flow."""

    # We setup the client here so if at some point we add any other entity for this device,
    # we will be able to properly share the connection.
    uuid = config_entry.data[CONF_ENTRY_ID]
    host = config_entry.data[CONF_ENTRY_HOST]

    hass.data.setdefault(DOMAIN, {})[uuid] = TweakedTwinklyClient(
        host, async_get_clientsession(hass)
    )

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(config_entry, "light")
    )
    return True


async def async_unload_entry(hass: HomeAssistantType, config_entry: ConfigEntry):
    """Remove a twinkly entry."""

    # For now light entries don't have unload method, so we don't have to async_forward_entry_unload
    # However we still have to cleanup the shared client!
    uuid = config_entry.data[CONF_ENTRY_ID]
    hass.data[DOMAIN].pop(uuid)

    return True


class TweakedTwinklyClient(twinkly_client.TwinklyClient):
    """Client of the Twinkly API."""

    def __init__(self, host: str, session: ClientSession = None):
        """Initialize a TwinklyClient."""
        self.details: Dict[str, Union[str, int]] = {}

        super().__init__(host, session)

    async def __auth(self) -> None:
        """Authenticate to the device."""
        # _LOGGER.info("Authenticating to '%s'", self._host)

        # Login to the device using a hard-coded challenge
        login_response = await self._session.post(
            url=self._base_url + twinkly_client.EP_LOGIN,
            json={"challenge": "Uswkc0TgJDmwl5jrsyaYSwY8fqeLJ1ihBLAwYcuADEo="},
            raise_for_status=True,
            timeout=twinkly_client.EP_TIMEOUT,
        )
        login_result = await login_response.json()
        # _LOGGER.debug("Successfully logged-in to '%s'", self._host)

        # Get the token, but do not store it until it gets verified
        token = login_result["authentication_token"]

        # Verify the token is valid
        await self._session.post(
            url=self._base_url + twinkly_client.EP_VERIFY,
            headers={"X-Auth-Token": token},
            raise_for_status=True,
            timeout=twinkly_client.EP_TIMEOUT,
        )
        # _LOGGER.debug("Successfully verified token to '%s'", self._host)

        self._token = token

    async def __send_request(
        self, endpoint: str, data: Any = None, raw=None, retry: int = 1, headers=None
    ) -> Any:
        """Send an authenticated request with auto retry if not yet auth."""
        if self._token is None:
            await self.__auth()

        header = {"X-Auth-Token": self._token}
        if headers is not None:
            header.update(headers)

        try:
            if raw is not None:
                response = await self._session.request(
                    method="GET" if data is None else "POST",
                    url=self._base_url + endpoint,
                    data=raw,
                    headers=header,
                    raise_for_status=True,
                    timeout=twinkly_client.EP_TIMEOUT,
                )
            else:
                response = await self._session.request(
                    method="GET" if data is None else "POST",
                    url=self._base_url + endpoint,
                    json=data,
                    headers=header,
                    raise_for_status=True,
                    timeout=twinkly_client.EP_TIMEOUT,
                )
            result = await response.json() if data is None else None
            return result
        except ClientResponseError as err:
            if err.code == 401 and retry > 0:
                self._token = None
                return await self.__send_request(endpoint, data, retry - 1)
            raise

    @property
    def length(self) -> int:
        """Get length."""
        return int(self.details["number_of_led"])

    async def interview(self) -> None:
        """Interview."""
        if len(self.details) == 0:
            self.details = await self.get_device_info()

    async def set_mode(self, mode: str) -> Any:
        """Set mode."""
        await self.__send_request(twinkly_client.EP_MODE, {"mode": mode})

    async def set_movie_config(self, data: dict) -> Any:
        """Set movie config."""
        return await self.__send_request("led/movie/config", data=data)

    async def upload_movie(self, movie: bytes) -> Any:
        """Upload movie."""
        return await self.__send_request(
            "led/movie/full",
            raw=movie,
            headers={"Content-Type": "application/octet-stream"},
        )

    async def set_static_colour(self, colour) -> None:
        """Set static color."""
        await self.interview()
        frame = [colour for _ in range(0, self.length)]
        movie = bytes([item for t in frame for item in t])
        await self.upload_movie(movie)
        await self.set_movie_config(
            {
                "frames_number": 1,
                "loop_type": 0,
                "frame_delay": 56,
                "leds_number": self.length,
            }
        )
        await self.set_mode("movie")

from __future__ import annotations

from typing import Optional


class APIKeyNotSetError(ValueError):
    """Raised when API key has not been set."""


class Config:
    """
    Configuration class for managing the API key and providing the API endpoint.

    Attributes:
        _api_key (Optional[str]): The stored API key. Defaults to None.
    """

    _api_key: Optional[str] = None

    @classmethod
    def set_api_key(cls, apikey: str):
        """
        Set the API key without validation.

        Raises:
            ValueError: Empty key.
        """
        if not isinstance(apikey, str) or not apikey.strip():
            raise ValueError("API key must be a non-empty string.")
        cls._api_key = apikey.strip()

    @classmethod
    def get_api_key(cls) -> str:
        """
        Retrieve the currently set API key.

        Raises:
            APIKeyNotSetError: If the API key has not been set.
        """
        if cls._api_key is None:
            raise APIKeyNotSetError(
                "API key is not set. Use client(apikey=...) to set it."
            )
        return cls._api_key

    @classmethod
    def get_link(cls) -> str:
        """Return the API base URL."""
        return "https://d207hp2u5nyjgn.cloudfront.net"


def client(apikey: str):
    """
    Convenience function to set the API key.
    """
    Config.set_api_key(apikey)

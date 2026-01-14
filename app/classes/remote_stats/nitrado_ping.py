import json
import httpx
import logging

logger = logging.getLogger(__name__)


class NitradoPing:

    @staticmethod
    def ping(ip: str, port: int) -> dict:
        """Pings server query URL and port looking for Nitrado stats plugin on hytale
        server https://github.com/nitrado/hytale-plugin-query

        Args:
            ip (str): IP of server instance
            port (int): Port of server instance

        Returns:
            dict: returns dict response with structure defined in nitrado query docs
        """
        url = f"https://{ip}:{port}"
        try:
            response = httpx.get(url, timeout=1)
        except (httpx.ConnectTimeout, httpx.ConnectError):
            logger.debug("Failed to get stats from Hytale server")
            return {}
        return json.loads(response.json())

    @staticmethod
    def parse_ping_response(response: dict) -> dict:
        """Parses dict object with response from ping

        Args:
            response (dict): Dict object from ping method call

        Returns:
            tuple: length of three tuple server data, universe data, player data
        """
        server = response.get("Server", {})
        universe = response.get("Universe", {})
        players = response.get("Players", [])
        return {
            "online": universe.get("CurrentPlayers", 0),
            "max": server.get("MaxPlayers", 0),
            "players": players,
            "server_description": server.get("Name", False),
            "server_version": server.get("Version", False),
            "server_icon": None,
        }

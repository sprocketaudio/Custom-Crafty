import sys
import logging

logger = logging.Logger(__name__)


class OS(Enum):
    LINUX = "linux"
    WINDOWS = "windows"


class SteamGame:
    def __init__(self, input_dict: dict[str, str | bool | list[str]]):
        try:
            self.name: str = input_dict["name"]
            self.id: str = str(input_dict["id"])
            self.anonymous: bool = input_dict["anonymous"]
            os_list: list[str] = input_dict["os"]
        except KeyError as why:
            logger.error(f"error reading steamcmd config: {why}")
            sys.exit(1)

        self.os: list[OS] = []

        for os in os_list:
            if os == "linux":
                self.os.append(OS.LINUX)
            if os == "windows":
                self.os.append(OS.WINDOWS)


class SteamCMD:
    def __init__(self, input_dict: dict[str, int | dict[str, str | bool | list[str]]]):
        self.version: int = input_dict["version"]
        self.games: list[SteamGame] = [SteamGame(g) for g in input_dict["games"]]

    def get_game_id_dict(self) -> dict[str, str]:
        return {g.name == g.id for g in self.games}

    def get_list_of_games_by_os(self, os: OS | None) -> list[SteamGame]:
        """if you just want a list of game obejcts by given os"""
        match os:
            case None:
                return self.games
            case default:
                return [g for g in self.games if g.os == os]

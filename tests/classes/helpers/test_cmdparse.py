import pytest

from app.classes.helpers.helpers import Helpers


@pytest.mark.parametrize(
    ("raw_command", "expected_argv"),
    [
        (
            "java -Xms1024M -Xmx2048M -jar server.jar nogui",
            ["java", "-Xms1024M", "-Xmx2048M", "-jar", "server.jar", "nogui"],
        ),
        (
            'java -Xms1024M -Xmx2048M -jar "Paper Server.jar" nogui',
            ["java", "-Xms1024M", "-Xmx2048M", "-jar", "Paper Server.jar", "nogui"],
        ),
        (
            "java -Xms2048M -Xmx2048M -jar Server/HytaleServer.jar --assets Assets.zip --bind 0.0.0.0:5517",
            [
                "java",
                "-Xms2048M",
                "-Xmx2048M",
                "-jar",
                "Server/HytaleServer.jar",
                "--assets",
                "Assets.zip",
                "--bind",
                "0.0.0.0:5517",
            ],
        ),
        (
            '"C:\\Servers\\My Bedrock\\bedrock_server.exe"',
            [r"C:\Servers\My Bedrock\bedrock_server.exe"],
        ),
        (
            "java -jar 'My Server.jar' nogui",
            ["java", "-jar", "My Server.jar", "nogui"],
        ),
        (
            r"java -jar My\ Server.jar nogui",
            ["java", "-jar", r"My\ Server.jar", "nogui"],
        ),
        (
            r'java -Dmotd=\"Hello\" -jar server.jar',
            ["java", '-Dmotd="Hello"', "-jar", "server.jar"],
        ),
        (
            "   java    -jar    server.jar   ",
            ["java", "-jar", "server.jar"],
        ),
    ],
)
def test_cmdparse_regression_examples(raw_command: str, expected_argv: list[str]) -> None:
    """Regression fixtures for launch commands used by create/import server flows."""
    assert Helpers.cmdparse(raw_command) == expected_argv

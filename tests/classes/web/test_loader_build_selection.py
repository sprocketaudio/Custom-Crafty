from types import SimpleNamespace

from app.classes.big_bucket.bigbucket import BigBucket
from app.classes.web.routes.api.servers.index import ApiServersIndexHandler
import app.classes.web.routes.api.servers.index as servers_index


def test_loader_build_urls_target_official_installer_artifacts():
    assert BigBucket.get_loader_fetch_url("forge-installer", "1.21.1-52.1.0") == (
        "https://maven.minecraftforge.net/net/minecraftforge/forge/"
        "1.21.1-52.1.0/forge-1.21.1-52.1.0-installer.jar"
    )
    assert BigBucket.get_loader_fetch_url("neoforge-installer", "21.1.140") == (
        "https://maven.neoforged.net/releases/net/neoforged/neoforge/"
        "21.1.140/neoforge-21.1.140-installer.jar"
    )
    assert BigBucket.get_loader_fetch_url("neoforge-installer", "../../bad") is None


def test_loader_build_list_filters_forge_and_neoforge_by_minecraft_version(monkeypatch):
    metadata = """
        <metadata><versioning><versions>
          <version>1.21.1-52.1.0</version>
          <version>1.21.1-52.1.1</version>
          <version>1.20.1-47.3.0</version>
          <version>21.1.138</version>
          <version>21.1.140</version>
          <version>21.0.167</version>
        </versions></versioning></metadata>
    """
    monkeypatch.setattr(
        servers_index.requests,
        "get",
        lambda *_args, **_kwargs: SimpleNamespace(
            text=metadata, raise_for_status=lambda: None
        ),
    )

    assert ApiServersIndexHandler._loader_versions("forge-installer", "1.21.1") == [
        "1.21.1-52.1.1",
        "1.21.1-52.1.0",
    ]
    assert ApiServersIndexHandler._loader_versions("neoforge-installer", "1.21.1") == [
        "21.1.140",
        "21.1.138",
    ]

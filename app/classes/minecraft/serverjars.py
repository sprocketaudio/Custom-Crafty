import os
import json
import threading
import time
import logging
from datetime import datetime
import requests

from app.classes.controllers.servers_controller import ServersController
from app.classes.models.server_permissions import PermissionsServers
from app.classes.shared.file_helpers import FileHelpers
from app.classes.shared.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)
# Temp type var until sjars restores generic fetchTypes
SERVERJARS_TYPES = ["modded", "proxies", "servers", "vanilla"]
PAPERJARS = ["paper", "folia"]


class ServerJars:
    def __init__(self, helper):
        self.helper = helper
        self.base_url = "https://api.serverjars.com"
        self.paper_base = "https://api.papermc.io"

    @staticmethod
    def get_paper_jars():
        return PAPERJARS

    def get_paper_versions(self, project):
        """
        Retrieves a list of versions for a specified project from the PaperMC API.

        Parameters:
            project (str): The project name to query for available versions.

        Returns:
            list: A list of version strings available for the project. Returns an empty
                list if the API call fails or if no versions are found.

        This function makes a GET request to the PaperMC API to fetch available project
        versions, The versions are returned in reverse order, with the most recent
        version first.
        """
        try:
            response = requests.get(
                f"{self.paper_base}/v2/projects/{project}/", timeout=2
            )
            response.raise_for_status()
            api_data = response.json()
        except Exception as e:
            logger.error(f"Error loading project versions for {project}: {e}")
            return []

        versions = api_data.get("versions", [])
        versions.reverse()  # Ensure the most recent version comes first
        return versions

    def get_paper_build(self, project, version):
        """
        Fetches the latest build for a specified project and version from PaperMC API.

        Parameters:
            project (str): Project name, typically a server software like 'paper'.
            version (str): Project version to fetch the build number for.

        Returns:
            int or None: Latest build number if successful, None if not or on error.

        This method attempts to query the PaperMC API for the latest build and
        handles exceptions by logging errors and returning None.
        """
        try:
            response = requests.get(
                f"{self.paper_base}/v2/projects/{project}/versions/{version}/builds/",
                timeout=2,
            )
            response.raise_for_status()
            api_data = response.json()
        except Exception as e:
            logger.error(f"Error fetching build for {project} {version}: {e}")
            return None

        builds = api_data.get("builds", [])
        return builds[-1] if builds else None

    def _read_cache(self):
        cache_file = self.helper.serverjar_cache
        cache = {}
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)

        except Exception as e:
            logger.error(f"Unable to read serverjars.com cache file: {e}")

        return cache

    def get_serverjar_data(self):
        data = self._read_cache()
        return data.get("types")

    def _check_sjars_api_alive(self):
        logger.info("Checking serverjars.com API status")

        check_url = f"{self.base_url}"
        try:
            response = requests.get(check_url, timeout=2)
            response_json = response.json()

            if (
                response.status_code in [200, 201]
                and response_json.get("status") == "success"
                and response_json.get("response", {}).get("status") == "ok"
            ):
                logger.info("Serverjars.com API is alive and responding as expected")
                return True
        except Exception as e:
            logger.error(f"Unable to connect to serverjar.com API due to error: {e}")
            return False

        logger.error(
            "Serverjars.com API is not responding as expected or unable to contact"
        )
        return False

    def _fetch_projects_for_type(self, server_type):
        """
        Fetches projects for a given server type from the ServerJars API.
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/fetchTypes/{server_type}", timeout=5
            )
            response.raise_for_status()  # Ensure HTTP errors are caught
            data = response.json()
            if data.get("status") == "success":
                return data["response"].get("servers", [])
        except requests.RequestException as e:
            print(f"Error fetching projects for type {server_type}: {e}")
        return []

    def _get_server_type_list(self):
        """
        Builds the type structure with projects fetched for each type.
        """
        type_structure = {}
        for server_type in SERVERJARS_TYPES:
            projects = self._fetch_projects_for_type(server_type)
            type_structure[server_type] = {project: [] for project in projects}
        return type_structure

    def _get_jar_versions(self, server_type, project_name):
        """
        Grabs available versions per project
        """
        url = f"{self.base_url}/api/fetchAll/{server_type}/{project_name}"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()  # Ensure HTTP errors are caught
            data = response.json()
            logger.debug(f"Received data for {server_type}/{project_name}: {data}")

            if data.get("status") == "success":
                versions = [
                    item.get("version")
                    for item in data.get("response", [])
                    if "version" in item
                ]
                logger.debug(f"Versions extracted: {versions}")
                return versions
        except requests.RequestException as e:
            logger.error(
                f"Error fetching jar versions for {server_type}/{project_name}: {e}"
            )

        return []

    def _refresh_cache(self):
        """
        Contains the shared logic for refreshing the cache.
        This method is called by both manual_refresh_cache and refresh_cache methods.
        """
        now = datetime.now()
        cache_data = {
            "last_refreshed": now.strftime("%m/%d/%Y, %H:%M:%S"),
            "types": self._get_server_type_list(),
        }

        for server_type, projects in cache_data["types"].items():
            for project_name in projects:
                versions = self._get_jar_versions(server_type, project_name)
                cache_data["types"][server_type][project_name] = versions

        for paper_project in PAPERJARS:
            cache_data["types"]["servers"][paper_project] = self.get_paper_versions(
                paper_project
            )

        return cache_data

    def manual_refresh_cache(self):
        """
        Manually triggers the cache refresh process.
        """
        if not self._check_sjars_api_alive():
            logger.error("ServerJars API is not available.")
            return False

        logger.info("Manual cache refresh requested.")
        cache_data = self._refresh_cache()

        # Save the updated cache data
        try:
            with open(self.helper.serverjar_cache, "w", encoding="utf-8") as cache_file:
                json.dump(cache_data, cache_file, indent=4)
                logger.info("Cache file successfully refreshed manually.")
        except Exception as e:
            logger.error(f"Failed to update cache file manually: {e}")

    def refresh_cache(self):
        """
        Automatically trigger cache refresh process based age.

        This method checks if the cache file is older than a specified number of days
        before deciding to refresh.
        """
        cache_file_path = self.helper.serverjar_cache

        # Determine if the cache is old and needs refreshing
        cache_old = self.helper.is_file_older_than_x_days(cache_file_path)

        # debug override
        # cache_old = True

        if not self._check_sjars_api_alive():
            logger.error("ServerJars API is not available.")
            return False

        if not cache_old:
            logger.info("Cache file is not old enough to require automatic refresh.")
            return False

        logger.info("Automatic cache refresh initiated due to old cache.")
        cache_data = self._refresh_cache()

        # Save the updated cache data
        try:
            with open(cache_file_path, "w", encoding="utf-8") as cache_file:
                json.dump(cache_data, cache_file, indent=4)
                logger.info("Cache file successfully refreshed automatically.")
        except Exception as e:
            logger.error(f"Failed to update cache file automatically: {e}")

    def get_fetch_url(self, jar, server, version):
        """
        Constructs the URL for downloading a server JAR file based on the server type.

        Supports two main types of server JAR sources:
        - ServerJars API for servers not in PAPERJARS.
        - Paper API for servers available through the Paper project.

        Parameters:
            jar (str): Name of the JAR file.
            server (str): Server software name (e.g., "paper").
            version (str): Server version.

        Returns:
            str or None: URL for downloading the JAR file, or None if URL cannot be
                        constructed or an error occurs.
        """
        try:
            # Check if the server type is not specifically handled by Paper.
            if server not in PAPERJARS:
                return f"{self.base_url}/api/fetchJar/{jar}/{server}/{version}"

            # For Paper servers, attempt to get the build for the specified version.
            paper_build_info = self.get_paper_build(server, version)
            if paper_build_info is None:
                # Log an error or handle the case where paper_build_info is None
                logger.error(
                    "Error: Unable to get build information for server:"
                    f" {server}, version: {version}"
                )
                return None

            build = paper_build_info.get("build")
            if not build:
                # Log an error or handle the case where build is None or not found
                logger.error(
                    f"Error: Build number not found for server:"
                    f" {server}, version: {version}"
                )
                return None

            # Construct and return the URL for downloading the Paper server JAR.
            return (
                f"{self.paper_base}/v2/projects/{server}/versions/{version}/"
                f"builds/{build}/downloads/{server}-{version}-{build}.jar"
            )
        except Exception as e:
            logger.error(f"An error occurred while constructing fetch URL: {e}")
            return None

    def download_jar(self, jar, server, version, path, server_id):
        update_thread = threading.Thread(
            name=f"server_download-{server_id}-{server}-{version}",
            target=self.a_download_jar,
            daemon=True,
            args=(jar, server, version, path, server_id),
        )
        update_thread.start()

    def a_download_jar(self, jar, server, version, path, server_id):
        """
        Downloads a server JAR file and performs post-download actions including
        notifying users and setting import status.

        This method waits for the server registration to complete, retrieves the
        download URL for the specified server JAR file.

        Upon successful download, it either runs the installer for
        Forge servers or simply finishes the import process for other types. It
        notifies server users about the completion of the download.

        Parameters:
            - jar (str): The name of the JAR file to download.
            - server (str): The type of server software (e.g., 'forge', 'paper').
            - version (str): The version of the server software.
            - path (str): The local filesystem path where the JAR file will be saved.
            - server_id (str): The unique identifier for the server being updated or
                imported, used for notifying users and setting the import status.

        Returns:
            - bool: True if the JAR file was successfully downloaded and saved;
                False otherwise.

        The method ensures that the server is properly registered before proceeding
        with the download and handles exceptions by logging errors and reverting
        the import status if necessary.
        """
        # delaying download for server register to finish
        time.sleep(3)

        fetch_url = self.get_fetch_url(jar, server, version)
        if not fetch_url:
            return False

        server_users = PermissionsServers.get_server_user_list(server_id)

        # Make sure the server is registered before updating its stats
        while True:
            try:
                ServersController.set_import(server_id)
                for user in server_users:
                    WebSocketManager().broadcast_user(user, "send_start_reload", {})
                break
            except Exception as ex:
                logger.debug(f"Server not registered yet. Delaying download - {ex}")

        # Initiate Download
        jar_dir = os.path.dirname(path)
        jar_name = os.path.basename(path)
        logger.info(fetch_url)
        success = FileHelpers.ssl_get_file(fetch_url, jar_dir, jar_name)

        # Post-download actions
        if success:
            if server == "forge":
                # If this is the newer Forge version, run the installer
                ServersController.finish_import(server_id, True)
            else:
                ServersController.finish_import(server_id)

            # Notify users
            for user in server_users:
                WebSocketManager().broadcast_user(
                    user, "notification", "Executable download finished"
                )
                time.sleep(3)  # Delay for user notification
                WebSocketManager().broadcast_user(user, "send_start_reload", {})
        else:
            logger.error(f"Unable to save jar to {path} due to download failure.")
            ServersController.finish_import(server_id)

        return success

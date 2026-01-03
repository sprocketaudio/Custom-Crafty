import os
import time
import shutil
import pathlib
import logging
import threading

from app.classes.controllers.server_perms_controller import PermissionsServers
from app.classes.controllers.servers_controller import ServersController
from app.classes.helpers.helpers import Helpers
from app.classes.helpers.file_helpers import FileHelpers
from app.classes.shared.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


class ImportHelpers:
    allowed_quotes = ['"', "'", "`"]

    def __init__(self, helper, file_helper):
        self.file_helper: FileHelpers = file_helper
        self.helper: Helpers = helper

    def import_zipped_server(
        self,
        archive_path,
        new_server_dir,
        base_include_path,
        port,
        new_id,
        full_exe_path=None,
    ):
        import_thread = threading.Thread(
            target=self.import_threaded_zipped_server,
            daemon=True,
            args=(
                archive_path,
                new_server_dir,
                base_include_path,
                port,
                new_id,
                full_exe_path,
            ),
            name=f"{new_id}_import",
        )
        import_thread.start()

    def import_threaded_zipped_server(
        self,
        archive_path,
        new_server_dir,
        base_include_path,
        port,
        new_id,
        full_exe_path,
    ):
        self.file_helper.unzip_file(
            archive_path,
            new_server_dir,
            new_id,
            False,
            base_include_path=base_include_path,
        )

        if (
            not self.helper.is_os_windows() and full_exe_path
        ):  # we only expect full jar path for bedrock
            if Helpers.check_file_exists(full_exe_path):
                os.chmod(full_exe_path, 0o2760)  # apply execute permissions

        self.file_helper.del_file(archive_path)

        has_properties = False
        for item in os.listdir(new_server_dir):
            if str(item) == "server.properties":
                has_properties = True
        if not has_properties:
            logger.info(
                f"No server.properties found on zip file import. "
                f"Creating one with port selection of {str(port)}"
            )
            with open(
                os.path.join(new_server_dir, "server.properties"), "w", encoding="utf-8"
            ) as file:
                file.write(f"server-port={port}")
                file.close()
        time.sleep(5)
        ServersController.finish_import(new_id)
        server_users = PermissionsServers.get_server_user_list(new_id)
        for user in server_users:
            WebSocketManager().broadcast_user(user, "send_start_reload", {})

    def download_bedrock_server(self, path, new_id):
        bedrock_url = Helpers.get_latest_bedrock_url()
        download_thread = threading.Thread(
            target=self.download_threaded_bedrock_server,
            daemon=True,
            args=(path, new_id, bedrock_url),
            name=f"{new_id}_download",
        )
        download_thread.start()

    def download_threaded_bedrock_server(
        self, path, new_id, bedrock_url, server_update=False
    ):
        """
        Downloads the latest Bedrock server, unzips it, sets necessary permissions.

        Parameters:
            path (str): The directory path to download and unzip the Bedrock server.
            new_id (str): The identifier for the new server import operation.

        This method handles exceptions and logs errors for each step of the process.
        """
        try:
            if bedrock_url:
                file_path = os.path.join(path, "bedrock_server.zip")
                success = FileHelpers.ssl_get_file(
                    bedrock_url, path, "bedrock_server.zip"
                )
                if not success:
                    logger.error("Failed to download the Bedrock server zip.")
                    return

                unzip_path = self.helper.wtol_path(file_path)
                destination_path = pathlib.Path(unzip_path).parents[0]
                # unzips archive that was downloaded.
                self.file_helper.unzip_file(
                    unzip_path, destination_path, new_id, server_update=server_update
                )
                # adjusts permissions for execution if os is not windows

                if not self.helper.is_os_windows():
                    os.chmod(os.path.join(path, "bedrock_server"), 0o0744)

                # we'll delete the zip we downloaded now
                os.remove(file_path)
            else:
                logger.error("Bedrock download URL issue!")
        except Exception as e:
            logger.critical(
                f"Failed to download bedrock executable during server creation! \n{e}"
            )
            raise e

        ServersController.finish_import(new_id)
        server_users = PermissionsServers.get_server_user_list(new_id)
        for user in server_users:
            WebSocketManager().broadcast_user(user, "send_start_reload", {})

import os
import time
import datetime
import json
import logging

from zoneinfo import ZoneInfo

# TZLocal is set as a hidden import on win pipeline
from zoneinfo import ZoneInfoNotFoundError
from tzlocal import get_localzone

from app.classes.models.management import HelpersManagement
from app.classes.models.users import HelperUsers
from app.classes.models.server_permissions import PermissionsServers
from app.classes.shared.console import Console
from app.classes.shared.helpers import Helpers
from app.classes.shared.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


class BackupManager:
    def __init__(self, helper, file_helper, management_helper):
        self.helper = helper
        self.file_helper = file_helper
        self.management_helper = management_helper
        try:
            self.tz = get_localzone()
        except ZoneInfoNotFoundError as e:
            logger.error(
                "Could not capture time zone from system. Falling back to Europe/London"
                f" error: {e}"
            )
            self.tz = ZoneInfo("Europe/London")

    def backup_starter(self, backup_config, server):
        if backup_config.get("type", "zip_vault") == "zip_vault":
            self.zip_vault(backup_config, server)

    def zip_vault(self, backup_config, server):

        logger.info(f"Starting server {server.name}" f" (ID {server.server_id}) backup")
        server_users = PermissionsServers.get_server_user_list(server.server_id)
        # Alert the start of the backup to the authorized users.
        for user in server_users:
            WebSocketManager().broadcast_user(
                user,
                "notification",
                self.helper.translation.translate(
                    "notify", "backupStarted", HelperUsers.get_user_lang_by_id(user)
                ).format(server.name),
            )
        time.sleep(3)

        # Adjust the location to include the backup ID for destination.
        backup_location = os.path.join(
            backup_config["backup_location"], backup_config["backup_id"]
        )

        # Check if the backup location even exists.
        if not backup_location:
            Console.critical("No backup path found. Canceling")
            return None

        self.helper.ensure_dir_exists(backup_location)

        try:
            backup_filename = (
                f"{backup_location}/"
                f"{datetime.datetime.now().astimezone(self.tz).strftime('%Y-%m-%d_%H-%M-%S')}"  # pylint: disable=line-too-long
            )
            logger.info(
                f"Creating backup of server {server.name}"
                f" (ID#{server.server_id}, path={server.server_path}) "
                f"at '{backup_filename}'"
            )
            excluded_dirs = HelpersManagement.get_excluded_backup_dirs(
                backup_config["backup_id"]
            )
            server_dir = Helpers.get_os_understandable_path(server.server_path)

            self.file_helper.make_backup(
                Helpers.get_os_understandable_path(backup_filename),
                server_dir,
                excluded_dirs,
                server.server_id,
                backup_config["backup_id"],
                backup_config["backup_name"],
                backup_config["compress"],
            )

            self.remove_old_backups(backup_config, server)

            logger.info(f"Backup of server: {server.name} completed")
            results = {
                "percent": 100,
                "total_files": 0,
                "current_file": 0,
                "backup_id": backup_config["backup_id"],
            }
            if len(WebSocketManager().clients) > 0:
                WebSocketManager().broadcast_page_params(
                    "/panel/server_detail",
                    {"id": str(server.server_id)},
                    "backup_status",
                    results,
                )
            server_users = PermissionsServers.get_server_user_list(server.server_id)
            for user in server_users:
                WebSocketManager().broadcast_user(
                    user,
                    "notification",
                    self.helper.translation.translate(
                        "notify",
                        "backupComplete",
                        HelperUsers.get_user_lang_by_id(user),
                    ).format(server.name),
                )
            # pause to let people read message.
            HelpersManagement.update_backup_config(
                backup_config["backup_id"],
                {"status": json.dumps({"status": "Standby", "message": ""})},
            )
            time.sleep(5)
        except Exception as e:
            logger.exception(
                "Failed to create backup of server"
                f" {server.name} (ID {server.server_id})"
            )
            results = {
                "percent": 100,
                "total_files": 0,
                "current_file": 0,
                "backup_id": backup_config["backup_id"],
            }
            if len(WebSocketManager().clients) > 0:
                WebSocketManager().broadcast_page_params(
                    "/panel/server_detail",
                    {"id": str(server.server_id)},
                    "backup_status",
                    results,
                )

            HelpersManagement.update_backup_config(
                backup_config["backup_id"],
                {"status": json.dumps({"status": "Failed", "message": f"{e}"})},
            )
        server.backup_server(
            backup_config,
        )

    def list_backups(self, backup_config: dict, server_id) -> list:
        if not backup_config:
            logger.info(
                f"Error putting backup file list for server with ID: {server_id}"
            )
            return []
        backup_location = os.path.join(
            backup_config["backup_location"],
            backup_config["backup_id"],
        )
        if not Helpers.check_path_exists(
            Helpers.get_os_understandable_path(backup_location)
        ):
            return []
        files = Helpers.get_human_readable_files_sizes(
            Helpers.list_dir_by_date(
                Helpers.get_os_understandable_path(backup_location)
            )
        )
        return [
            {
                "path": os.path.relpath(
                    f["path"],
                    start=Helpers.get_os_understandable_path(backup_location),
                ),
                "size": f["size"],
            }
            for f in files
            if f["path"].endswith(".zip")
        ]

    def remove_old_backups(self, backup_config, server):
        while (
            len(self.list_backups(backup_config, server)) > backup_config["max_backups"]
            and backup_config["max_backups"] > 0
        ):
            backup_list = self.list_backups(backup_config, server.server_id)
            oldfile = backup_list[0]
            oldfile_path = os.path.join(
                backup_config["backup_location"],
                backup_config["backup_id"],
                oldfile["path"],
            )
            logger.info(f"Removing old backup '{oldfile['path']}'")
            os.remove(Helpers.get_os_understandable_path(oldfile_path))

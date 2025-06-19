import datetime
import io
import json
import logging
import os
import shutil
import time
from pathlib import Path

# TZLocal is set as a hidden import on win pipeline
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tzlocal import get_localzone

from app.classes.helpers.cryptography_helper import CryptoHelper
from app.classes.helpers.file_helpers import FileHelpers
from app.classes.helpers.helpers import Helpers
from app.classes.models.management import HelpersManagement
from app.classes.models.server_permissions import PermissionsServers
from app.classes.models.users import HelperUsers
from app.classes.shared.console import Console
from app.classes.shared.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


class BackupManager:

    SNAPSHOT_BACKUP_DATE_FORMAT_STRING = "%Y-%m-%d-%H-%M-%S"

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

    def restore_starter(  # pylint: disable=too-many-positional-arguments
        self, backup_config, backup_location, backup_file, svr_obj, in_place
    ):
        server_path = svr_obj.settings["path"]
        if Helpers.validate_traversal(backup_location, backup_file):
            if svr_obj.check_running():
                svr_obj.stop_server()
            if backup_config["backup_type"] != "zip_vault":
                self.snapshot_restore(backup_config, backup_file, svr_obj)
            else:
                if not in_place:  # If user does not want to backup in place we will
                    # clean the server dir
                    for item in os.listdir(server_path):
                        if (
                            os.path.isdir(os.path.join(server_path, item))
                            and item != "db_stats"
                        ):
                            self.file_helper.del_dirs(os.path.join(server_path, item))
                        else:
                            self.file_helper.del_file(os.path.join(server_path, item))
                self.file_helper.restore_archive(backup_location, server_path)

    def backup_starter(self, backup_config, server):
        """Notify users of backup starting, and start the backup.

        Args:
            backup_config (_type_): _description_
            server (_type_): Server object to backup
        """
        # Notify users of backup starting
        logger.info(f"Starting server {server.name} (ID {server.server_id}) backup")
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

        # Start the backup
        if backup_config.get("backup_type", "zip_vault") == "zip_vault":
            self.zip_vault(backup_config, server)
        else:
            self.snapshot_backup(backup_config, server)

    def zip_vault(self, backup_config, server):

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
                f"""{datetime.datetime.now()
                   .astimezone(self.tz)
                   .strftime('%Y-%m-%d_%H-%M-%S')}"""
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
            self.fail_backup(e, backup_config, server)

    @staticmethod
    def fail_backup(why: Exception, backup_config: dict, server) -> None:
        """
        Fails the backup if an error is encountered during the backup.

        Args:
            why: Exception raised to fail backup.
            backup_config: Backup config dict
            server: Server object.

        Returns: None

        """
        logger.exception(
            "Failed to create backup of server"
            f" {server.name} (ID {server.server_id})"
        )
        results: dict = {
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
            {"status": json.dumps({"status": "Failed", "message": f"{why}"})},
        )

    @staticmethod
    def list_backups(backup_config: dict, server_id) -> list:
        if not backup_config:
            logger.info(
                f"Error putting backup file list for server with ID: {server_id}"
            )
            return []
        backup_location = os.path.join(
            backup_config["backup_location"],
            backup_config["backup_id"],
        )
        if backup_config["backup_type"] == "snapshot":
            backup_location = os.path.join(
                backup_config["backup_location"], "snapshot_backups", "manifests"
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
        if backup_config["backup_type"] == "snapshot":
            return [
                {
                    "path": os.path.relpath(
                        f["path"],
                        start=Helpers.get_os_understandable_path(backup_location),
                    ),
                    "size": "",
                }
                for f in files
                if f["path"].endswith(".manifest")
            ]
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

    def snapshot_backup(self, backup_config, server) -> None:
        """
        Creates snapshot style backup of server. No file will be saved more than once
        over all backups. Designed to enable encryption of files and s3 compatability in
        the future.

        Args:
            backup_config: Backup config to use.
            server: Server instance.

        Returns:

        """
        logger.info(f"Starting snapshot style backup for {server.name}")

        # Create backup variables.
        use_compression = backup_config["compress"]
        source_path = Path(server.server_path)
        backup_repository_path = (
            Path(backup_config["backup_location"]) / "snapshot_backups"
        )
        backup_time = datetime.datetime.now()
        backup_time_filesafe = backup_time.strftime(
            self.SNAPSHOT_BACKUP_DATE_FORMAT_STRING
        )
        backup_manifest_path = (
            backup_repository_path / "manifests" / f"{backup_time_filesafe}.manifest"
        )

        excluded_dirs = HelpersManagement.get_excluded_backup_dirs(
            backup_config["backup_id"]
        )
        list_of_files: list[Path] = FileHelpers.discover_files(
            source_path, excluded_dirs
        )

        # Create manifest file
        try:
            backup_manifest_path.parent.mkdir(exist_ok=True, parents=True)
            manifest_file: io.TextIOWrapper = backup_manifest_path.open("w+")
        except OSError as why:
            self.fail_backup(why, backup_config, server)
            return

        # Write manifest file version.
        manifest_file.write("00\n")

        # Iterate over source files and save into backup repository.
        for file in list_of_files:
            try:
                file_hash = CryptoHelper.blake2_hash_file(file)
                self.file_helper.save_file(
                    file, backup_repository_path, file_hash, use_compression
                )
                # May return OSError if file path is not logical.
                file_local_path = self.file_helper.get_local_path_with_base(
                    file, source_path
                )
            except OSError as why:
                manifest_file.close()
                backup_manifest_path.unlink(missing_ok=True)
                self.fail_backup(why, backup_config, server)
                return

            # Write saved file into manifest.
            manifest_file.write(
                f"{CryptoHelper.bytes_to_b64(file_hash)}:"
                f"{CryptoHelper.str_to_b64(file_local_path)}\n"
            )

        manifest_file.close()

        self.file_helper.clean_old_backups(
            backup_config["max_backups"], backup_repository_path
        )

    def snapshot_restore(
        self, backup_config: {str}, backup_manifest_filename: str, server
    ) -> None:
        """
        Restores snapshot style backup.

        Args:
            backup_config: Backup Config.
            backup_manifest_filename: Filename of backup manifest.
            server: Server config.

        Returns:
        """
        destination_path = Path(server.settings["path"])
        source_manifest_path = Path(
            backup_config["backup_location"],
            "snapshot_backups",
            "manifests",
            backup_manifest_filename,
        )
        # /snapshot_backups/manifests/manifest.manifest
        backup_repository_path = source_manifest_path.parent.parent

        # Ensure destination is not a file.
        if destination_path.is_file():
            raise RuntimeError(
                f"Destination path {destination_path} for restore is a file."
            )

        # Ensure target is empty.
        if destination_path.exists():
            shutil.rmtree(destination_path)

        # Ensure target directory exists.
        destination_path.mkdir(exist_ok=True, parents=True)

        # Open backup manifest.
        try:
            backup_manifest_file: io.TextIOWrapper = source_manifest_path.open(
                "r", encoding="utf-8"
            )
        except OSError as why:
            raise RuntimeError(
                f"Unable to open backup manifest at {source_manifest_path}."
            ) from why

        # Ensure backup manifest is of readable version.
        if backup_manifest_file.readline() != "00\n":
            backup_manifest_file.close()
            raise RuntimeError(
                f"Backup manifest file {source_manifest_path} is of unreadable "
                f"version."
            )

        # Begin restoring files from manifest.
        for file_hash_and_path in backup_manifest_file:
            hash_and_local_path: list[str] = file_hash_and_path.split(":")
            file_hash: bytes = CryptoHelper.b64_to_bytes(hash_and_local_path[0])
            recovered_file_path: Path = Path(
                destination_path,
                CryptoHelper.b64_to_str(input_b64=hash_and_local_path[1]),
            ).resolve()

            # Recover file
            try:
                self.file_helper.read_file(
                    file_hash, recovered_file_path, backup_repository_path
                )
            except RuntimeError as why:
                backup_manifest_file.close()
                raise RuntimeError(f"Unable to recover file {file_hash}.") from why

        # Restore complete, close backup manifest file.
        backup_manifest_file.close()

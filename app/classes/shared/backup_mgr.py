import os
import time
import datetime
import json
import logging
import pathlib

from zoneinfo import ZoneInfo

# TZLocal is set as a hidden import on win pipeline
from zoneinfo import ZoneInfoNotFoundError
from tzlocal import get_localzone

from app.classes.models.management import HelpersManagement
from app.classes.models.users import HelperUsers
from app.classes.models.server_permissions import PermissionsServers
from app.classes.shared.console import Console
from app.classes.helpers.helpers import Helpers
from app.classes.shared.websocket_manager import WebSocketManager
from app.classes.helpers.file_helpers import FileHelpers
from app.classes.web.webhooks.base_webhook import helper

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
        """Notify users of backup starting, and start the backup.

        Args:
            backup_config (_type_): _description_
            server (_type_): Server object to backup
        """
        # Notify users of backup starting
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
        server.backup_server(
            backup_config,
        )

    def fail_backup(self, why: Exception, backup_config: dict, server):
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
            {"status": json.dumps({"status": "Failed", "message": f"{why}"})},
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

    def snapshot_backup(self, backup_config, server):

        logger.info(f"Starting snapshot style backup for {server.name}")

        # Adjust the location to include the backup ID for destination.
        backup_target_location = (
            pathlib.Path(backup_config["backup_location"]) / "snapshot_backups"
        )
        try:
            self.ensure_snapshot_directory_is_valid(backup_target_location)
        except PermissionError as why:
            self.fail_backup(why, backup_config, server)

        # Create backup manifest for server files.
        backup_manifest, count_of_files = self.create_snapshot_backup_manifest(
            pathlib.Path(server.server_path)
        )

        # Generate depends file for this backup.
        self.create_depends_file_from_backup_manifest(
            backup_manifest, backup_target_location, backup_config["backup_id"]
        )

    @staticmethod
    def ensure_snapshot_directory_is_valid(backup_path: pathlib.Path) -> bool:
        backup_path.mkdir(exist_ok=True)
        backup_readme_path = backup_path / "README.txt"

        if not backup_readme_path.exists():
            logger.info("Is this doing anything?")
            try:
                logger.info("Attempting to make snapshot storage directory.")
                with open(backup_readme_path, "w", encoding="UTF-8") as f:
                    f.write(
                        "Crafty snapshot backup storage dir. Please do not touch"
                        "these files."
                    )

            except PermissionError as why:
                raise PermissionError(
                    f"Unable to write to snapshot backup storage path"
                    f": {backup_readme_path}"
                ) from why
        return True

    @staticmethod
    def get_local_path_with_base(desired_path: pathlib.Path, base: pathlib.Path) -> str:
        """Takes a given path with a given base, and removes the base from the path.

        Example:
            # Base: /root/crafty/servers
            # Full path to file: /root/crafty/servers/path/to/dir
            # What gets returned: path/to/dir

        """
        # Check that path is contained in base
        if base not in desired_path.parents:
            raise ValueError(
                f"{base} does not appear to be a base directory of {desired_path}."
            )

        # Return path with base remove
        return str(desired_path)[len(str(base.absolute())) + 1 :]

    def create_snapshot_backup_manifest(self, backup_dir: pathlib.Path) -> (dict, int):
        """
        Creates dict showing all directories in backup source as a relative path, and
        all files with their hashes as a relative path. All returned paths are relative
        to the root of the server.

        Args:
            backup_dir: Path to files that need to be backed up.

        Returns: Dict {directories: [], "files": [()]}
            File hashes are calculated as raw bytes and encoded in base64 strings.

        """
        output = {"directories": [], "files": []}
        files_count = 0

        # Iterate over backups source dir.
        for p in backup_dir.rglob("*"):

            if p.is_dir():
                # For files.
                # Append local path to dir. For example:
                # Base: /root/crafty/servers
                # Full path to file: /root/crafty/servers/path/to/dir
                # What gets stored: path/to/dir
                output["directories"].append(
                    str(self.get_local_path_with_base(p, backup_dir))
                )

            else:
                # For files.
                files_count += 1

                # We must store file hash and path to file.
                # calculate_file_hash_blake2b returns bytes, b64 is stored as a string.
                file_hash = helper.crypto_helper.bytes_to_b64(
                    FileHelpers.calculate_file_hash_blake2b(p)
                )

                # Store tuple for file with local path and b64 hash.
                output["files"].append(
                    (file_hash, str(self.get_local_path_with_base(p, backup_dir)))
                )
        return output, files_count

    @staticmethod
    def create_depends_file_from_backup_manifest(
        manifest: dict, backup_repository: pathlib.Path, backup_id: str
    ) -> None:
        """
        Creates the .depends file associated with this backup based on the backup's
        manifest.

        Args:
            manifest: Backup manifest for this backup.
            backup_repository: Where the backup is being stored as a pathlib Path
            object.
            backup_id: Backup's ID as a string.

        Returns: None

        """
        # Create file path for depends file
        depends_file_path = (
            backup_repository / "manifest_files" / f"{backup_id}.depends"
        )

        # Ensure manifest_files folder exists
        depends_file_path.parent.mkdir(exist_ok=True)

        # Write base64 encoded hashes to depends file. This file may not contain
        # sensitive information as it will not be encrypted.
        with depends_file_path.open("x", encoding="UTF-8") as f:
            # Append version number to file.
            f.write("1\n")
            # Iterate through files and add b64 hashes to file.
            for depended_file in manifest["files"]:
                f.write(depended_file[0] + "\n")

    def find_files_not_in_repository(
        self, backup_manifest: dict, backup_repository: pathlib.Path
    ) -> list[(str, str)]:
        """
        Discovers what files are not already contained in the backup repository by hash.
        Returns a hash of files that are not in the repository in backup manifest
        format.

        Args:
            self: self
            backup_manifest: backup manifest as generated by
            create_snapshot_backup_manifest.
            backup_repository: Path to the backup storage location or backup
            "repository."

        Returns: List of files that are not in the repository in backup manifest format.
        [(file hash), (file name)]

        """
        output = []

        # If file does not exist add it array.
        for file_tuple in backup_manifest["files"]:
            file_path = self.get_path_from_hash(file_tuple[0], backup_repository)
            if not file_path.exists():
                output.append(file_tuple)
        return output

    @staticmethod
    def get_path_from_hash(file_hash: str, repository: pathlib.Path) -> pathlib.Path:
        """
        Get file path in backup repository based on file hash and path to the backup
        repository.

        Args:
            file_hash: Hash of target file.
            repository: Path to the backup repository.

        Returns: Path to where file should be stored.

        """
        # Example:
        # Repo path: /path/to/backup/repo/
        # Hash: 1234...890
        # Example: /path/to/backup/repo/data/12/34...890
        file_hash = helper.crypto_helper.b64_to_bytes(file_hash)
        file_hash = helper.crypto_helper.bytes_to_hex(file_hash)
        return repository / "data" / file_hash[:2] / str(file_hash[-126:])

    # TODO: Implement this function to save all new chunks using save_chunk.
    # @staticmethod
    # def save_chunks_from_manifest(
    #     self, backup_manifest: dict, backup_repository: pathlib.Path
    # ):
    #
    #     files_to_save = self.find_files_not_in_repository(
    #         backup_manifest, backup_repository
    #     )
    #
    #     for file_tuple in files_to_save:
    #         save_chunk(file_tuple[0], file_tuple[1])

    def save_chunk(
        self,
        file: bytes,
        repository_location: pathlib.Path,
        file_hash: str,
        use_compression: bool = False,
    ):
        # Chunk Schema version
        output = bytes.fromhex("00")

        # Append zero bytes for compression bool and nonce. Will be used later for
        # encryption. 1 byte bool and 12 bytes of nonce.
        output += bytes.fromhex("00000000000000000000000000")

        # Compress chunk if set
        # Append compression byte to output bytes.
        if use_compression:
            file = helper.file_helper.zlib_compress_bytes(file)
            output += bytes.fromhex("01")
        else:
            output += bytes.fromhex("00")

        # Output matches version 1 schema.
        # version + encryption byte + nonce + compression byte + file bytes
        # Reuse file var to prevent extra memory. Not sure if python would do that but
        # avoiding it anyway.
        file = output + file

        # Get file location and save to location
        # TODO: This b64 -> bytes -> hex is being done twice for every file to save.
        #  Change this so that bytes are being passed around and this is minimized.
        file_hash = helper.crypto_helper.b64_to_bytes(file_hash)
        file_hash = helper.crypto_helper.bytes_to_hex(file_hash)
        file_location = self.get_path_from_hash(file_hash, repository_location)

        # Saves file, double check it does not already exist.
        if not file_location.exists():
            with file_location.open("wb") as f:
                f.write(file)

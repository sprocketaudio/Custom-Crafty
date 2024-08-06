import os
import shutil
import logging
import pathlib
import tempfile
import zipfile
import hashlib
from typing import BinaryIO
import mimetypes
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
import urllib.request
import ssl
import time
import certifi

from app.classes.shared.helpers import Helpers
from app.classes.shared.console import Console
from app.classes.shared.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


class FileHelpers:
    allowed_quotes = ['"', "'", "`"]

    def __init__(self, helper):
        self.helper: Helpers = helper
        self.mime_types = mimetypes.MimeTypes()

    @staticmethod
    def ssl_get_file(
        url, out_path, out_file, max_retries=3, backoff_factor=2, headers=None
    ):
        """
        Downloads a file from a given URL using HTTPS with SSL context verification,
        retries with exponential backoff and providing download progress feedback.

        Parameters:
            - url (str): The URL of the file to download. Must start with "https".
            - out_path (str): The local path where the file will be saved.
            - out_file (str): The name of the file to save the downloaded content as.
            - max_retries (int, optional): The maximum number of retry attempts
                in case of download failure. Defaults to 3.
            - backoff_factor (int, optional): The factor by which the wait time
                increases after each failed attempt. Defaults to 2.
            - headers (dict, optional):
                A dictionary of HTTP headers to send with the request.

        Returns:
            - bool: True if the download was successful, False otherwise.

        Raises:
            - urllib.error.URLError: If a URL error occurs during the download.
            - ssl.SSLError: If an SSL error occurs during the download.
        Exception: If an unexpected error occurs during the download.

        Note:
        This method logs critical errors and download progress information.
        Ensure that the logger is properly configured to capture this information.
        """
        if not url.lower().startswith("https"):
            logger.error("SSL File Get - Error: URL must start with https.")
            return False

        ssl_context = ssl.create_default_context(cafile=certifi.where())

        if not headers:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/58.0.3029.110 Safari/537.3"
                )
            }
        req = urllib.request.Request(url, headers=headers)

        write_path = os.path.join(out_path, out_file)
        attempt = 0

        logger.info(f"SSL File Get - Requesting remote: {url}")
        file_path_full = os.path.join(out_path, out_file)
        logger.info(f"SSL File Get - Download Destination: {file_path_full}")

        while attempt < max_retries:
            try:
                with urllib.request.urlopen(req, context=ssl_context) as response:
                    total_size = response.getheader("Content-Length")
                    if total_size:
                        total_size = int(total_size)
                    downloaded = 0
                    with open(write_path, "wb") as file:
                        while True:
                            chunk = response.read(1024 * 1024)  # 1 MB
                            if not chunk:
                                break
                            file.write(chunk)
                            downloaded += len(chunk)
                            if total_size:
                                progress = (downloaded / total_size) * 100
                                logger.info(
                                    f"SSL File Get - Download progress: {progress:.2f}%"
                                )
                    return True
            except (urllib.error.URLError, ssl.SSLError) as e:
                logger.warning(f"SSL File Get - Attempt {attempt+1} failed: {e}")
                time.sleep(backoff_factor**attempt)
            except Exception as e:
                logger.critical(f"SSL File Get - Unexpected error: {e}")
                return False
            finally:
                attempt += 1

        logger.error("SSL File Get - Maximum retries reached. Download failed.")
        return False

    @staticmethod
    def del_dirs(path):
        path = pathlib.Path(path)
        for sub in path.iterdir():
            if sub.is_dir():
                # Delete folder if it is a folder
                FileHelpers.del_dirs(sub)
            else:
                # Delete file if it is a file:
                try:
                    sub.unlink()
                except:
                    logger.error(f"Unable to delete file {sub}")
        try:
            # This removes the top-level folder:
            path.rmdir()
        except Exception as e:
            logger.error("Unable to remove top level")
            return e
        return True

    @staticmethod
    def del_file(path):
        path = pathlib.Path(path)
        try:
            logger.debug(f"Deleting file: {path}")
            # Remove the file
            os.remove(path)
            return True
        except (FileNotFoundError, PermissionError) as e:
            logger.error(f"Path specified is not a file or does not exist. {path}")
            return e

    def check_mime_types(self, file_path):
        m_type, _value = self.mime_types.guess_type(file_path)
        return m_type

    @staticmethod
    def calculate_file_hash(file_path: str) -> str:
        """
        Takes one parameter of file path.
        It will generate a SHA256 hash for the path and return it.
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    @staticmethod
    def calculate_buffer_hash(buffer: BinaryIO) -> str:
        """
        Takes one argument of a stream buffer. Will return a
        sha256 hash of the buffer
        """
        sha256_hash = hashlib.sha256()
        sha256_hash.update(buffer)
        return sha256_hash.hexdigest()

    @staticmethod
    def copy_dir(src_path, dest_path, dirs_exist_ok=False):
        # pylint: disable=unexpected-keyword-arg
        shutil.copytree(src_path, dest_path, dirs_exist_ok=dirs_exist_ok)

    @staticmethod
    def copy_file(src_path, dest_path):
        shutil.copy(src_path, dest_path)

    @staticmethod
    def move_dir(src_path, dest_path):
        shutil.move(src_path, dest_path)

    @staticmethod
    def move_dir_exist(src_path, dest_path):
        FileHelpers.copy_dir(src_path, dest_path, True)
        FileHelpers.del_dirs(src_path)

    @staticmethod
    def move_file(src_path, dest_path):
        shutil.move(src_path, dest_path)

    @staticmethod
    def make_archive(path_to_destination, path_to_zip, comment=""):
        # create a ZipFile object
        path_to_destination += ".zip"
        with ZipFile(path_to_destination, "w") as zip_file:
            zip_file.comment = bytes(
                comment, "utf-8"
            )  # comments over 65535 bytes will be truncated
            for root, _dirs, files in os.walk(path_to_zip, topdown=True):
                ziproot = path_to_zip
                for file in files:
                    try:
                        logger.info(f"backing up: {os.path.join(root, file)}")
                        if os.name == "nt":
                            zip_file.write(
                                os.path.join(root, file),
                                os.path.join(root.replace(ziproot, ""), file),
                            )
                        else:
                            zip_file.write(
                                os.path.join(root, file),
                                os.path.join(root.replace(ziproot, "/"), file),
                            )

                    except Exception as e:
                        logger.warning(
                            f"Error backing up: {os.path.join(root, file)}!"
                            f" - Error was: {e}"
                        )
        return True

    @staticmethod
    def make_compressed_archive(path_to_destination, path_to_zip, comment=""):
        # create a ZipFile object
        path_to_destination += ".zip"
        with ZipFile(path_to_destination, "w", ZIP_DEFLATED) as zip_file:
            zip_file.comment = bytes(
                comment, "utf-8"
            )  # comments over 65535 bytes will be truncated
            for root, _dirs, files in os.walk(path_to_zip, topdown=True):
                ziproot = path_to_zip
                for file in files:
                    try:
                        logger.info(f"packaging: {os.path.join(root, file)}")
                        if os.name == "nt":
                            zip_file.write(
                                os.path.join(root, file),
                                os.path.join(root.replace(ziproot, ""), file),
                            )
                        else:
                            zip_file.write(
                                os.path.join(root, file),
                                os.path.join(root.replace(ziproot, "/"), file),
                            )

                    except Exception as e:
                        logger.warning(
                            f"Error packaging: {os.path.join(root, file)}!"
                            f" - Error was: {e}"
                        )

        return True

    def make_backup(
        self,
        path_to_destination,
        path_to_zip,
        excluded_dirs,
        server_id,
        backup_id,
        comment="",
        compressed=None,
    ):
        # create a ZipFile object
        path_to_destination += ".zip"
        ex_replace = [p.replace("\\", "/") for p in excluded_dirs]
        total_bytes = 0
        dir_bytes = Helpers.get_dir_size(path_to_zip)
        results = {
            "percent": 0,
            "total_files": self.helper.human_readable_file_size(dir_bytes),
        }
        WebSocketManager().broadcast_page_params(
            "/panel/server_detail",
            {"id": str(server_id)},
            "backup_status",
            results,
        )
        WebSocketManager().broadcast_page_params(
            "/panel/edit_backup",
            {"id": str(server_id)},
            "backup_status",
            results,
        )
        # Set the compression mode based on the `compressed` parameter
        compression_mode = ZIP_DEFLATED if compressed else ZIP_STORED
        with ZipFile(path_to_destination, "w", compression_mode) as zip_file:
            zip_file.comment = bytes(
                comment, "utf-8"
            )  # comments over 65535 bytes will be truncated
            for root, dirs, files in os.walk(path_to_zip, topdown=True):
                for l_dir in dirs[:]:
                    # make all paths in exclusions a unix style slash
                    # to match directories.
                    if str(os.path.join(root, l_dir)).replace("\\", "/") in ex_replace:
                        dirs.remove(l_dir)
                ziproot = path_to_zip
                # iterate through list of files
                for file in files:
                    # check if file/dir is in exclusions list.
                    # Only proceed if not exluded.
                    if (
                        str(os.path.join(root, file)).replace("\\", "/")
                        not in ex_replace
                        and file != "crafty.sqlite"
                    ):
                        try:
                            logger.debug(f"backing up: {os.path.join(root, file)}")
                            # add trailing slash to zip root dir if not windows.
                            if os.name == "nt":
                                zip_file.write(
                                    os.path.join(root, file),
                                    os.path.join(root.replace(ziproot, ""), file),
                                )
                            else:
                                zip_file.write(
                                    os.path.join(root, file),
                                    os.path.join(root.replace(ziproot, "/"), file),
                                )

                        except Exception as e:
                            logger.warning(
                                f"Error backing up: {os.path.join(root, file)}!"
                                f" - Error was: {e}"
                            )
                    # debug logging for exlusions list
                    else:
                        logger.debug(f"Found {file} in exclusion list. Skipping...")

                    # add current file bytes to total bytes.
                    total_bytes += os.path.getsize(os.path.join(root, file))
                    # calcualte percentage based off total size and current archive size
                    percent = round((total_bytes / dir_bytes) * 100, 2)
                    # package results
                    results = {
                        "percent": percent,
                        "total_files": self.helper.human_readable_file_size(dir_bytes),
                        "backup_id": backup_id,
                    }
                    # send status results to page.
                    WebSocketManager().broadcast_page_params(
                        "/panel/server_detail",
                        {"id": str(server_id)},
                        "backup_status",
                        results,
                    )
                    WebSocketManager().broadcast_page_params(
                        "/panel/edit_backup",
                        {"id": str(server_id)},
                        "backup_status",
                        results,
                    )
        return True

    @staticmethod
    def unzip_file(zip_path, server_update=False):
        ignored_names = ["server.properties", "permissions.json", "allowlist.json"]
        # Get directory without zipfile name
        new_dir = pathlib.Path(zip_path).parents[0]
        # make sure we're able to access the zip file
        if Helpers.check_file_perms(zip_path) and os.path.isfile(zip_path):
            # make sure the directory we're unzipping this to exists
            Helpers.ensure_dir_exists(new_dir)
            # we'll make a temporary directory to unzip this to.
            temp_dir = tempfile.mkdtemp()
            try:
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    # we'll extract this to the temp dir using zipfile module
                    zip_ref.extractall(temp_dir)
                # we'll iterate through the top level directory moving everything
                # out of the temp directory and into it's final home.
                for item in os.listdir(temp_dir):
                    # if the file is one of our ignored names we'll skip it
                    if item in ignored_names and server_update:
                        continue
                    # we handle files and dirs differently or we'll crash out.
                    if os.path.isdir(os.path.join(temp_dir, item)):
                        try:
                            FileHelpers.move_dir_exist(
                                os.path.join(temp_dir, item),
                                os.path.join(new_dir, item),
                            )
                        except Exception as ex:
                            logger.error(f"ERROR IN ZIP IMPORT: {ex}")
                    else:
                        try:
                            FileHelpers.move_file(
                                os.path.join(temp_dir, item),
                                os.path.join(new_dir, item),
                            )
                        except Exception as ex:
                            logger.error(f"ERROR IN ZIP IMPORT: {ex}")
            except Exception as ex:
                Console.error(ex)
        else:
            return "false"
        return

    def unzip_server(self, zip_path, user_id):
        if Helpers.check_file_perms(zip_path):
            temp_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # extracts archive to temp directory
                zip_ref.extractall(temp_dir)
            if user_id:
                return temp_dir

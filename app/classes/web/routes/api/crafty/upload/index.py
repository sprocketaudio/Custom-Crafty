import os
import logging
import json
import shutil
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from app.classes.models.server_permissions import EnumPermissionsServer
from app.classes.shared.helpers import Helpers
from app.classes.shared.main_controller import WebSocketManager, Controller
from app.classes.web.base_api_handler import BaseApiHandler


class ApiFilesUploadHandler(BaseApiHandler):
    async def post(self, server_id=None):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        upload_type = self.request.headers.get("type")

        if server_id:
            if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
                # if the user doesn't have access to the server, return an error
                return self.finish_json(
                    400, {"status": "error", "error": "NOT_AUTHORIZED"}
                )
            mask = self.controller.server_perms.get_lowest_api_perm_mask(
                self.controller.server_perms.get_user_permissions_mask(
                    auth_data[4]["user_id"], server_id
                ),
                auth_data[5],
            )
            server_permissions = self.controller.server_perms.get_permissions(mask)
            if EnumPermissionsServer.FILES not in server_permissions:
                # if the user doesn't have Files permission, return an error
                return self.finish_json(
                    400, {"status": "error", "error": "NOT_AUTHORIZED"}
                )

            u_type = "server_upload"
        elif auth_data[4]["superuser"] and upload_type == "background":
            u_type = "admin_config"
            self.upload_dir = os.path.join(
                self.controller.project_root,
                "app/frontend/static/assets/images/auth/custom",
            )
        elif upload_type == "import":
            if (
                not self.controller.crafty_perms.can_create_server(
                    auth_data[4]["user_id"]
                )
                and not auth_data[4]["superuser"]
            ):
                return self.finish_json(
                    400,
                    {
                        "status": "error",
                        "error": "NOT_AUTHORIZED",
                        "data": {"message": ""},
                    },
                )
            self.upload_dir = os.path.join(
                self.controller.project_root, "import", "upload"
            )
            u_type = "server_import"
        else:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "data": {"message": ""},
                },
            )
        # Get the headers from the request
        fileHash = self.request.headers.get("fileHash", 0)
        chunkHash = self.request.headers.get("chunk-hash", 0)
        self.file_id = self.request.headers.get("fileId")
        self.chunked = self.request.headers.get("chunked", True)
        self.filename = self.request.headers.get("filename", None)
        try:
            file_size = int(self.request.headers.get("fileSize", None))
            total_chunks = int(self.request.headers.get("total_chunks", None))
        except TypeError:
            return self.finish_json(
                400, {"status": "error", "error": "TYPE ERROR", "data": {}}
            )
        self.chunk_index = self.request.headers.get("chunkId")
        if u_type == "server_upload":
            self.upload_dir = self.request.headers.get("location", None)
        self.temp_dir = os.path.join(self.controller.project_root, "temp", self.file_id)

        if u_type == "server_upload":
            full_path = os.path.join(self.upload_dir, self.filename)

            if not self.helper.is_subdir(
                full_path,
                Helpers.get_os_understandable_path(
                    self.controller.servers.get_server_data_by_id(server_id)["path"]
                ),
            ):
                return self.finish_json(
                    400,
                    {
                        "status": "error",
                        "error": "NOT AUTHORIZED",
                        "data": {"message": "Traversal detected"},
                    },
                )

        _total, _used, free = shutil.disk_usage(self.upload_dir)

        # Check to see if we have enough space
        if free <= file_size:
            return self.finish_json(
                507,
                {
                    "status": "error",
                    "error": "NO STORAGE SPACE",
                    "data": {"message": "Out Of Space!"},
                },
            )

        # If this has no chunk index we know it's the inital request
        if self.chunked and not self.chunk_index:
            return self.finish_json(
                200, {"status": "ok", "data": {"file-id": self.file_id}}
            )

        if not self.chunked:
            with open(os.path.join(self.upload_dir, self.filename), "wb") as file:
                while True:
                    chunk = self.request.body
                    if not chunk:
                        break
                    file.write(chunk)
            self.finish_json(
                200,
                {
                    "status": "completed",
                    "data": {"message": "File uploaded successfully"},
                },
            )

        # Create the upload and temp directories if they don't exist
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

        # Read headers and query parameters
        content_length = int(self.request.headers.get("Content-Length"))
        if content_length <= 0:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID CONTENT LENGTH",
                    "data": {"message": "Invalid content length"},
                },
            )

        if not self.filename or self.chunk_index is None or total_chunks is None:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INDEX ERROR",
                    "data": {
                        "message": "Filename, chunk_index,"
                        " and total_chunks are required"
                    },
                },
            )

        # File paths
        file_path = os.path.join(self.upload_dir, self.filename)
        chunk_path = os.path.join(
            self.temp_dir, f"{self.filename}.part{self.chunk_index}"
        )

        # Save the chunk
        with open(chunk_path, "wb") as f:
            f.write(self.request.body)

        # Check if all chunks are received
        received_chunks = [
            f
            for f in os.listdir(self.temp_dir)
            if f.startswith(f"{self.filename}.part")
        ]
        if len(received_chunks) == total_chunks:
            with open(file_path, "wb") as outfile:
                for i in range(total_chunks):
                    chunk_file = os.path.join(self.temp_dir, f"{self.filename}.part{i}")
                    with open(chunk_file, "rb") as infile:
                        outfile.write(infile.read())
                    os.remove(chunk_file)

            self.finish_json(
                200,
                {
                    "status": "completed",
                    "data": {"message": "File uploaded successfully"},
                },
            )
        else:
            self.write(
                json.dumps(
                    {
                        "status": "partial",
                        "message": f"Chunk {self.chunk_index} received",
                    }
                )
            )

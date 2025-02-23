import os
import logging
import json
import html
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from app.classes.models.crafty_permissions import EnumPermissionsCrafty
from app.classes.shared.helpers import Helpers
from app.classes.web.base_api_handler import BaseApiHandler
from app.classes.web.websocket_handler import WebSocketManager

logger = logging.getLogger(__name__)
files_get_schema = {
    "type": "object",
    "properties": {
        "page": {
            "type": "string",
            "minLength": 1,
            "error": "filesPageLen",
            "fill": True,
        },
        "folder": {"type": "string", "error": "typeString", "fill": True},
        "upload": {
            "type": "boolean",
            "default": "False",
            "error": "typeBool",
            "fill": True,
        },
        "unzip": {
            "type": "boolean",
            "default": "True",
            "error": "typeBool",
            "fill": True,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}


class ApiImportFilesIndexHandler(BaseApiHandler):
    def post(self):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        if (
            EnumPermissionsCrafty.SERVER_CREATION
            not in self.controller.crafty_perms.get_crafty_permissions_list(
                auth_data[4]["user_id"]
            )
            and not auth_data[4]["superuser"]
        ):
            # if the user doesn't have Files or Backup permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": "INSUFFICEN PERMISSIONS",
                },
            )

        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )
        try:
            validate(data, files_get_schema)
        except ValidationError as why:
            offending_key = ""
            if why.schema.get("fill", None):
                offending_key = why.path[0] if why.path else None
            err = f"""{offending_key} {self.translator.translate(
                "validators",
                why.schema.get("error"),
                self.controller.users.get_user_lang_by_id(auth_data[4]["user_id"]),
            )} {why.schema.get("enum", "")}"""
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_JSON_SCHEMA",
                    "error_data": f"{str(err)}",
                },
            )
        # TODO: limit some columns for specific permissions?
        folder = data["folder"]
        user_id = auth_data[4]["user_id"]
        root_path = False
        if data["unzip"]:
            # This is awful. Once uploads go to return
            # JSON we need to remove this and just send
            # the path.
            if data["upload"]:
                folder = os.path.join(
                    self.controller.project_root, "import", "upload", folder
                )
            if Helpers.check_file_exists(folder):
                folder = self.file_helper.unzip_server(folder, user_id)
                root_path = True
            else:
                if user_id:
                    user_lang = self.controller.users.get_user_lang_by_id(user_id)
                    WebSocketManager().broadcast_user(
                        user_id,
                        "send_start_error",
                        {
                            "error": self.helper.translation.translate(
                                "error", "no-file", user_lang
                            )
                        },
                    )
        else:
            if not self.helper.check_path_exists(folder) and user_id:
                user_lang = self.controller.users.get_user_lang_by_id(user_id)
                WebSocketManager().broadcast_user(
                    user_id,
                    "send_start_error",
                    {
                        "error": self.helper.translation.translate(
                            "error", "no-file", user_lang
                        )
                    },
                )
        return_json = {
            "root_path": {
                "path": folder,
                "top": root_path,
            }
        }

        dir_list = []
        unsorted_files = []
        file_list = os.listdir(folder)
        for item in file_list:
            if os.path.isdir(os.path.join(folder, item)):
                dir_list.append(item)
            else:
                unsorted_files.append(item)
        file_list = sorted(dir_list, key=str.casefold) + sorted(
            unsorted_files, key=str.casefold
        )
        for raw_filename in file_list:
            filename = html.escape(raw_filename)
            rel = os.path.join(folder, raw_filename)
            dpath = os.path.join(folder, filename)
            dpath = self.helper.wtol_path(dpath)
            if os.path.isdir(rel):
                return_json[filename] = {
                    "path": dpath,
                    "dir": True,
                }
            else:
                return_json[filename] = {
                    "path": dpath,
                    "dir": False,
                }
        self.finish_json(200, {"status": "ok", "data": return_json})

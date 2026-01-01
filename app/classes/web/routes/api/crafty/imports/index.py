import os
import logging
import json
import html
import zipfile
from pathlib import PurePath, Path
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from app.classes.models.crafty_permissions import EnumPermissionsCrafty
from app.classes.helpers.helpers import Helpers
from app.classes.web.base_api_handler import BaseApiHandler
from app.classes.web.websocket_handler import WebSocketManager

logger = logging.getLogger(__name__)
files_get_schema = {
    "type": "object",
    "properties": {
        "file_name": {"type": "string", "error": "typeString", "fill": True},
        "local_path": {"type": "string", "error": "typeString", "fill": True},
    },
    "additionalProperties": False,
    "minProperties": 1,
}


class ApiImportFilesIndexHandler(BaseApiHandler):
    def post(self):
        root_path = False
        # Disable pylint. This is a constant variable
        IMPORT_PATH = Path(  # pylint: disable=invalid-name
            self.controller.project_root, "import", "upload"
        )
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
                why.schema.get("error", "additionalProperties"),
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
        return_json = {
            "top": data["local_path"] == "",
            "request_path": data["local_path"],
        }
        if data["local_path"] != "":
            data["local_path"] += "/"
        path = zipfile.Path(
            Path(IMPORT_PATH, data["file_name"]), at=str(data["local_path"])
        )
        print(path.iterdir())
        for file in path.iterdir():
            if file.is_dir():
                return_json[file.name] = {
                    "path": str(
                        file.relative_to(Path(IMPORT_PATH, data.get("file_name")))
                    ),
                    "dir": True,
                }
            else:
                return_json[file.name] = {
                    "path": str(
                        file.relative_to(Path(IMPORT_PATH, data.get("file_name")))
                    ),
                    "dir": False,
                }
        print(json.dumps(return_json, indent=4))
        return self.finish_json(200, {"status": "ok", "data": return_json})

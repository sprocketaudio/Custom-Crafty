import os
import logging
import json
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from app.classes.models.server_permissions import EnumPermissionsServer
from app.classes.web.base_api_handler import BaseApiHandler

logger = logging.getLogger(__name__)

backup_patch_schema = {
    "type": "object",
    "properties": {
        "backup_name": {"type": "string", "minLength": 3},
        "backup_location": {"type": "string", "minLength": 1},
        "max_backups": {"type": "integer"},
        "compress": {"type": "boolean"},
        "shutdown": {"type": "boolean"},
        "before": {"type": "string"},
        "after": {"type": "string"},
        "excluded_dirs": {"type": "array"},
    },
    "additionalProperties": False,
    "minProperties": 1,
}

basic_backup_patch_schema = {
    "type": "object",
    "properties": {
        "backup_name": {"type": "string", "minLength": 3},
        "max_backups": {"type": "integer"},
        "compress": {"type": "boolean"},
        "shutdown": {"type": "boolean"},
        "before": {"type": "string"},
        "after": {"type": "string"},
        "excluded_dirs": {"type": "array"},
    },
    "additionalProperties": False,
    "minProperties": 1,
}


class ApiServersServerBackupsIndexHandler(BaseApiHandler):
    def get(self, server_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.BACKUP not in server_permissions:
            # if the user doesn't have Schedule permission, return an error
            return self.finish_json(400, {"status": "error", "error": "NOT_AUTHORIZED"})
        self.finish_json(
            200, self.controller.management.get_backups_by_server(server_id)
        )

    def post(self, server_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )

        try:
            if auth_data[4]["superuser"]:
                validate(data, backup_patch_schema)
            else:
                validate(data, basic_backup_patch_schema)
        except ValidationError as e:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_JSON_SCHEMA",
                    "error_data": str(e),
                },
            )
        if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
            # if the user doesn't have access to the server, return an error
            return self.finish_json(400, {"status": "error", "error": "NOT_AUTHORIZED"})
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.BACKUP not in server_permissions:
            # if the user doesn't have Schedule permission, return an error
            return self.finish_json(400, {"status": "error", "error": "NOT_AUTHORIZED"})
        # Set the backup location automatically for non-super users. We should probably
        # make the default location configurable for SU eventually
        if not auth_data[4]["superuser"]:
            data["backup_location"] = os.path.join(self.helper.backup_path, server_id)
        data["server_id"] = server_id
        if not data.get("excluded_dirs", None):
            data["excluded_dirs"] = []
        self.controller.management.add_backup_config(data)
        return self.finish_json(200, {"status": "ok"})

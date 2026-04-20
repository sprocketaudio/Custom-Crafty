import json
import logging

from jsonschema import ValidationError, validate

from app.classes.models.server_permissions import EnumPermissionsServer
from app.classes.web.base_api_handler import BaseApiHandler

logger = logging.getLogger(__name__)


ops_patch_schema = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "error": "typeString",
            "fill": True,
        },
        "uuid": {
            "type": "string",
            "minLength": 1,
            "error": "typeString",
            "fill": True,
        },
        "level": {
            "type": "integer",
            "minimum": 1,
            "maximum": 4,
            "error": "typeInt",
            "fill": True,
        },
        "bypassesPlayerLimit": {
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
    },
    "additionalProperties": False,
}


class ApiServersServerOpsHandler(BaseApiHandler):
    def patch(self, server_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )

        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.PLAYERS not in server_permissions:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )

        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )

        try:
            validate(data, ops_patch_schema)
        except ValidationError as why:
            offending_key = ""
            if why.schema.get("fill", None):
                offending_key = why.path[0] if why.path else None
            err = f"""{offending_key} {self.translator.translate(
                "validators",
                why.schema.get("error", "additionalProperties"),
                self.controller.users.get_user_lang_by_id(auth_data[4]["user_id"]),
            )}"""
            return self.finish_json(
                400,
                {"status": "error", "error": "INVALID_PAYLOAD", "error_data": err},
            )

        target_name = data.get("name")
        target_uuid = data.get("uuid")
        if not target_name and not target_uuid:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_PAYLOAD",
                    "error_data": "Either name or uuid is required.",
                },
            )
        if "level" not in data and "bypassesPlayerLimit" not in data:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_PAYLOAD",
                    "error_data": "At least one editable field is required.",
                },
            )

        updated_entry = self.controller.servers.update_ops_player_entry(
            server_id=server_id,
            name=target_name,
            uuid=target_uuid,
            level=data.get("level"),
            bypasses_player_limit=data.get("bypassesPlayerLimit"),
        )
        if updated_entry is None:
            return self.finish_json(
                404,
                {
                    "status": "error",
                    "error": "NOT_FOUND",
                    "error_data": "Could not find that OP entry in ops.json",
                },
            )

        target_repr = target_name or target_uuid
        self.controller.management.add_to_audit_log(
            auth_data[4]["user_id"],
            f"Updated ops.json entry for {target_repr}",
            server_id=server_id,
            source_ip=self.get_remote_ip(),
        )

        return self.finish_json(200, {"status": "ok", "data": updated_entry})

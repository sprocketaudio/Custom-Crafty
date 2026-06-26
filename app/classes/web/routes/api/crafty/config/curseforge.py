import json
from jsonschema import ValidationError, validate

from app.classes.web.base_api_handler import BaseApiHandler

curseforge_api_schema = {
    "type": "object",
    "properties": {
        "api_key": {
            "type": "string",
            "minLength": 0,
            "error": "typeString",
            "fill": True,
        }
    },
    "additionalProperties": False,
    "minProperties": 1,
}


class ApiCraftyConfigCurseForgeHandler(BaseApiHandler):
    def get(self):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        if not auth_data[4]["superuser"]:
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

        api_key = self.controller.management.get_curseforge_api_key() or ""
        masked = ""
        if api_key:
            if len(api_key) <= 8:
                masked = "*" * len(api_key)
            else:
                masked = f"{api_key[:4]}...{api_key[-4:]}"

        return self.finish_json(
            200,
            {"status": "ok", "data": {"configured": bool(api_key), "masked": masked}},
        )

    def patch(self):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        if not auth_data[4]["superuser"]:
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
        except json.decoder.JSONDecodeError as why:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(why)}
            )

        try:
            validate(data, curseforge_api_schema)
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

        api_key = data.get("api_key", "").strip()
        self.controller.management.set_curseforge_api_key(api_key)

        self.controller.management.add_to_audit_log(
            auth_data[4]["user_id"],
            "updated CurseForge API key",
            server_id=None,
            source_ip=self.get_remote_ip(),
        )

        return self.finish_json(200, {"status": "ok", "data": {"configured": bool(api_key)}})

import json
import logging
import typing as t

from playhouse.shortcuts import model_to_dict
from jsonschema import ValidationError, validate
from app.classes.controllers.users_controller import UsersController
from app.classes.models.crafty_permissions import EnumPermissionsCrafty
from app.classes.web.base_api_handler import BaseApiHandler


logger = logging.getLogger(__name__)

totp_schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 3},
    },
    "additionalProperties": False,
    "minProperties": 1,
}


class APIUsersTOTPIndexHandler(BaseApiHandler):
    def post(self, user_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return
        (
            _,
            exec_user_crafty_permissions,
            _,
            _,
            user,
            _,
        ) = auth_data
        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )

        try:
            validate(data, totp_schema)
        except ValidationError as e:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_JSON_SCHEMA",
                    "error_data": str(e),
                },
            )

        if user_id in ["@me", user["user_id"]]:
            user_id = user["user_id"]
            res_user = user
        elif EnumPermissionsCrafty.USER_CONFIG not in exec_user_crafty_permissions:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                },
            )
        else:
            # has User_Config permission and isn't viewing self
            res_user = self.controller.users.get_user_by_id(user_id)
            if not res_user:
                return self.finish_json(
                    404,
                    {
                        "status": "error",
                        "error": "USER_NOT_FOUND",
                    },
                )
        otp_name = data["name"]
        otp = self.controller.totp.create_user_totp(otp_name, user_id)
        recovery = self.controller.totp.create_missing_backup_codes(user_id)

        return self.finish_json(
            200,
            {
                "status": "ok",
                "data": {"otp": model_to_dict(otp), "backup_codes": recovery},
            },
        )

    def get(self, user_id: str, totp_id=None):
        auth_data = self.authenticate_user()
        if not auth_data:
            return
        (
            _,
            exec_user_crafty_permissions,
            _,
            _,
            user,
            _,
        ) = auth_data
        if totp_id:
            return

        if user_id in ["@me", user["user_id"]]:
            user_id = user["user_id"]
            res_user = self.controller.users.get_user_object(user_id)
        elif EnumPermissionsCrafty.USER_CONFIG not in exec_user_crafty_permissions:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                },
            )
        else:
            # has User_Config permission and isn't viewing self
            res_user = self.controller.users.get_user_object(user_id)
            if not res_user:
                return self.finish_json(
                    404,
                    {
                        "status": "error",
                        "error": "USER_NOT_FOUND",
                    },
                )

        codes = []
        user_totp = list(res_user.totp_user)
        for totp in user_totp:
            codes.append({"name": totp.name, "id": totp.id})

        self.finish_json(
            200,
            {"status": "ok", "data": codes},
        )


class APIUsersTOTPHandler(BaseApiHandler):
    def get(self, user_id: str, totp_id=None):
        auth_data = self.authenticate_user()
        if not auth_data:
            return
        (
            _,
            exec_user_crafty_permissions,
            _,
            _,
            user,
            _,
        ) = auth_data
        if totp_id:
            return

        if user_id in ["@me", user["user_id"]]:
            user_id = user["user_id"]
            res_user = self.controller.users.get_user_object(user_id)
        elif EnumPermissionsCrafty.USER_CONFIG not in exec_user_crafty_permissions:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                },
            )
        else:
            # has User_Config permission and isn't viewing self
            res_user = self.controller.users.get_user_object(user_id)
            if not res_user:
                return self.finish_json(
                    404,
                    {
                        "status": "error",
                        "error": "USER_NOT_FOUND",
                    },
                )

        codes = []
        user_totp = list(res_user.totp_user)
        for totp in user_totp:
            codes.append({"name": totp.name, "id": totp.id})

        self.finish_json(
            200,
            {"status": "ok", "data": codes},
        )

    def delete(self, user_id: str, totp_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return
        (
            _,
            exec_user_crafty_permissions,
            _,
            _,
            user,
            _,
        ) = auth_data
        if not totp_id:
            return self.finish_json(
                500,
                {
                    "status": "error",
                    "error": "INVALID_REQUEST",
                    "error_data": self.helper.translation.translate(
                        "userConfig",
                        "totpIdReq",
                        self.controller.users.get_user_lang_by_id(
                            auth_data[4]["user_id"]
                        ),
                    ),
                },
            )

        if user_id in ["@me", user["user_id"]]:
            user = self.controller.users.get_user_object(user_id)
            self.controller.users.remove_user(user_id)
        elif EnumPermissionsCrafty.USER_CONFIG not in exec_user_crafty_permissions:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                },
            )
        else:
            # has User_Config permission
            user = self.controller.users.get_user_object(user_id)
        if len(list(user.totp_user)) <= 1 and user.superuser:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "userConfig", "otpReq", self.helper.get_setting("language")
                    ),
                },
            )
        self.controller.totp.delete_user_totp(totp_id)
        self.controller.management.add_to_audit_log(
            user.user_id,
            f"deleted the user TOTP {totp_id}",
            server_id=None,
            source_ip=self.get_remote_ip(),
        )

        self.finish_json(
            200,
            {"status": "ok"},
        )

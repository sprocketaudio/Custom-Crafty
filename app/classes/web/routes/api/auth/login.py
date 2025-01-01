import logging
import json
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from app.classes.models.users import Users
from app.classes.shared.helpers import Helpers
from app.classes.web.base_api_handler import BaseApiHandler

logger = logging.getLogger(__name__)
auth_log = logging.getLogger("auth")
login_schema = {
    "type": "object",
    "properties": {
        "username": {
            "type": "string",
            "maxLength": 20,
            "minLength": 4,
            "pattern": "^[a-z0-9_]+$",
        },
        "password": {"type": "string", "minLength": 4},
    },
    "required": ["username", "password"],
    "additionalProperties": False,
}


class ApiAuthLoginHandler(BaseApiHandler):
    def post(self):
        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            logger.error(
                "Invalid JSON schema for API"
                f" login attempt from {self.get_remote_ip()}"
            )
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )

        try:
            validate(data, login_schema)
        except ValidationError as e:
            logger.error(
                "Invalid JSON schema for API"
                f" login attempt from {self.get_remote_ip()}"
            )
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_JSON_SCHEMA",
                    "error_data": str(e),
                },
            )

        username = data["username"]
        password = data["password"]

        # pylint: disable=no-member
        user_data = Users.get_or_none(Users.username == username)

        if user_data is None:
            self.controller.log_attempt(self.get_remote_ip(), username)
            auth_log.error(
                f"User attempted to log into {username}."
                " Authentication failed from remote IP"
                f" {self.get_remote_ip()}. User not found"
            )
            return self.finish_json(
                401,
                {
                    "status": "error",
                    "error": "INCORRECT_CREDENTIALS",
                    "error_data": "INVALID CREDENTIALS",
                    "token": None,
                },
            )

        if not user_data.enabled:
            auth_log.error(
                f"User attempted to log into {username}."
                " Authentication failed from remote"
                f" IP {self.get_remote_ip()} account disabled"
            )
            self.finish_json(
                403,
                {
                    "status": "error",
                    "error": "ACCOUNT_DISABLED",
                    "error_data": "ACCOUNT DISABLED",
                    "token": None,
                },
            )
            return

        login_result = self.helper.verify_pass(password, user_data.password)

        # Valid Login
        if login_result:
            auth_log.info(
                f"{username} successfully"
                " authenticated and logged"
                f" into panel from remote IP {self.get_remote_ip()}"
            )
            logger.info(f"User: {user_data} Logged in from IP: {self.get_remote_ip()}")

            # record this login
            query = Users.select().where(Users.username == username.lower()).get()
            query.last_ip = self.get_remote_ip()
            query.last_login = Helpers.get_time_as_string()
            query.save()

            # log this login
            self.controller.management.add_to_audit_log(
                user_data.user_id, "logged in via the API", None, self.get_remote_ip()
            )
            token = self.controller.authentication.generate(user_data.user_id)
            self.set_current_user(user_data.user_id, token)
            self.finish_json(
                200,
                {
                    "status": "ok",
                    "data": {
                        "token": token,
                        "user_id": str(user_data.user_id),
                        "page": "/panel/dashboard",
                    },
                },
            )
        else:
            # log this failed login attempt
            self.controller.management.add_to_audit_log(
                user_data.user_id, "Tried to log in", None, self.get_remote_ip()
            )
            self.controller.log_attempt(self.get_remote_ip(), username)
            # Setup error message for failed login
            error_msg = self.helper.translation.translate(
                "login", "incorrect", self.helper.get_setting("language")
            )
            if password == "app/config/default-creds.txt":
                error_msg += ". "
                error_msg += self.helper.translation.translate(
                    "login", "defaultPath", self.helper.get_setting("language")
                )
            self.finish_json(
                401,
                {
                    "status": "error",
                    "error": "INCORRECT_CREDENTIALS",
                    "error_data": error_msg,
                },
            )

    def set_current_user(self, user_id: str = None, token: str = None):
        expire_days = self.helper.get_setting("cookie_expire")

        # if helper comes back with false
        if not expire_days:
            expire_days = "5"

        if user_id is not None:
            self.set_cookie(
                "token",
                token,
                expires_days=int(expire_days),
            )
        else:
            self.clear_cookie("token")
            # self.clear_cookie("user")
            # self.clear_cookie("user_data")


class ApiAuthLoginHandler(BaseApiHandler):
    def post(self):
        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            logger.error(
                "Invalid JSON schema for API"
                f" login attempt from {self.get_remote_ip()}"
            )
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )

        try:
            validate(data, login_schema)
        except ValidationError as e:
            logger.error(
                "Invalid JSON schema for API"
                f" login attempt from {self.get_remote_ip()}"
            )
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_JSON_SCHEMA",
                    "error_data": str(e),
                },
            )

        username = data["username"]
        password = data["password"]

        # pylint: disable=no-member
        user_data = Users.get_or_none(Users.username == username)

        if user_data is None:
            self.controller.log_attempt(self.get_remote_ip(), username)
            auth_log.error(
                f"User attempted to log into {username}."
                " Authentication failed from remote IP"
                f" {self.get_remote_ip()}. User not found"
            )
            return self.finish_json(
                401,
                {
                    "status": "error",
                    "error": "INCORRECT_CREDENTIALS",
                    "error_data": "INVALID CREDENTIALS",
                    "token": None,
                },
            )

        if not user_data.enabled:
            auth_log.error(
                f"User attempted to log into {username}."
                " Authentication failed from remote"
                f" IP {self.get_remote_ip()} account disabled"
            )
            self.finish_json(
                403,
                {
                    "status": "error",
                    "error": "ACCOUNT_DISABLED",
                    "error_data": "ACCOUNT DISABLED",
                    "token": None,
                },
            )
            return

        login_result = self.helper.verify_pass(password, user_data.password)

        # Valid Login
        if login_result:
            auth_log.info(
                f"{username} successfully"
                " authenticated and logged"
                f" into panel from remote IP {self.get_remote_ip()}"
            )
            logger.info(f"User: {user_data} Logged in from IP: {self.get_remote_ip()}")

            # record this login
            query = Users.select().where(Users.username == username.lower()).get()
            query.last_ip = self.get_remote_ip()
            query.last_login = Helpers.get_time_as_string()
            query.save()

            # log this login
            self.controller.management.add_to_audit_log(
                user_data.user_id, "logged in via the API", None, self.get_remote_ip()
            )
            extra = None
            totp_req = False
            if list(user_data.totp_user) > 0:
                totp_req = True
                extra = {"type": "temp"}
            token = self.controller.authentication.generate(user_data.user_id, extra)
            self.set_current_user(user_data.user_id, token)
            self.finish_json(
                200,
                {
                    "status": "ok",
                    "data": {
                        "token": token,
                        "user_id": str(user_data.user_id),
                        "page": "/panel/dashboard",
                        "totp": totp_req,
                    },
                },
            )
        else:
            # log this failed login attempt
            self.controller.management.add_to_audit_log(
                user_data.user_id, "Tried to log in", None, self.get_remote_ip()
            )
            self.controller.log_attempt(self.get_remote_ip(), username)
            # Setup error message for failed login
            error_msg = self.helper.translation.translate(
                "login", "incorrect", self.helper.get_setting("language")
            )
            if password == "app/config/default-creds.txt":
                error_msg += ". "
                error_msg += self.helper.translation.translate(
                    "login", "defaultPath", self.helper.get_setting("language")
                )
            self.finish_json(
                401,
                {
                    "status": "error",
                    "error": "INCORRECT_CREDENTIALS",
                    "error_data": error_msg,
                },
            )

    def set_current_user(self, user_id: str = None, token: str = None):
        expire_days = self.helper.get_setting("cookie_expire")

        # if helper comes back with false
        if not expire_days:
            expire_days = "5"

        if user_id is not None:
            self.set_cookie(
                "token",
                token,
                expires_days=int(expire_days),
            )
        else:
            self.clear_cookie("token")
            # self.clear_cookie("user")
            # self.clear_cookie("user_data")

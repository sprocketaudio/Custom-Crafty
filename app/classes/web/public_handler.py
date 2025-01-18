import logging
import json
import nh3
from jsonschema import validate
from jsonschema.exceptions import ValidationError

from app.classes.shared.helpers import Helpers
from app.classes.models.users import HelperUsers
from app.classes.web.base_handler import BaseHandler

logger = logging.getLogger(__name__)
auth_log = logging.getLogger("auth")


class PublicHandler(BaseHandler):
    def set_current_user(self, user_id: str = None):
        expire_days = self.helper.get_setting("cookie_expire")

        # if helper comes back with false
        if not expire_days:
            expire_days = "5"

        if user_id is not None:
            self.set_cookie(
                "token",
                self.controller.authentication.generate(user_id),
                expires_days=int(expire_days),
            )
        else:
            self.clear_cookie("token")
            # self.clear_cookie("user")
            # self.clear_cookie("user_data")

    def get(self, page=None):
        # pylint: disable=no-member
        error = nh3.clean(self.get_argument("error", "Invalid Login!"))
        error_msg = nh3.clean(self.get_argument("error_msg", ""))
        # pylint: enable=no-member

        page_data = {
            "version": self.helper.get_version_string(),
            "error": error,
            "lang": self.helper.get_setting("language"),
            "lang_page": self.helper.get_lang_page(self.helper.get_setting("language")),
            "query": "",
            "background": self.controller.cached_login,
            "login_opacity": self.controller.management.get_login_opacity(),
            "themes": self.helper.get_themes(),
        }

        if self.request.query:
            request_query = self.request.query_arguments.get("next")
            if not request_query:
                self.redirect("/login")
            page_data["query"] = request_query[0].decode()

        # sensible defaults
        template = "public/404.html"

        if page == "login":
            template = "public/login.html"

        elif page == "404":
            template = "public/404.html"

        elif page == "error":
            template = "public/error.html"

        elif page == "offline":
            template = "public/offline.html"

        elif page == "logout":
            exec_user = self.get_current_user()
            self.clear_cookie("token")
            # Delete anti-lockout-user on lockout...it's one time use
            if exec_user[2]["username"] == "anti-lockout-user":
                self.controller.users.stop_anti_lockout()
            # self.clear_cookie("user")
            # self.clear_cookie("user_data")
            self.redirect("/login")
            return

        # if we have no page, let's go to login
        else:
            return self.redirect("/login")

        self.render(
            template,
            data=page_data,
            translate=self.translator.translate,
            error_msg=error_msg,
        )

    def post(self, page=None):
        login_schema = {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                },
                "password": {"type": "string"},
            },
            "required": ["username", "password"],
            "additionalProperties": False,
        }
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
                    "error": "VWggb2ghIFN0aW5reS 🪠",
                    "error_data": str(e),
                },
            )

        page_data = {
            "version": self.helper.get_version_string(),
            "lang": self.helper.get_setting("language"),
            "lang_page": self.helper.get_lang_page(self.helper.get_setting("language")),
            "query": "",
        }
        if self.request.query:
            page_data["query"] = self.request.query_arguments.get("next")[0].decode()

        if page == "login":
            data = json.loads(self.request.body)

            auth_log.info(
                f"User attempting to authenticate from {self.get_remote_ip()}"
            )
            entered_username = nh3.clean(data["username"])  # pylint: disable=no-member
            entered_password = data["password"]

            try:
                user_id = HelperUsers.get_user_id_by_name(entered_username.lower())
                user_data = HelperUsers.get_user_model(user_id)
            except:
                self.controller.log_attempt(self.get_remote_ip(), entered_username)
                auth_log.error(
                    f"User attempted to log into {entered_username}."
                    f" Authentication failed from remote IP {self.get_remote_ip()}"
                    " Users does not exist."
                )
                self.finish_json(
                    403,
                    {
                        "status": "error",
                        "error": self.helper.translation.translate(
                            "login", "incorrect", self.helper.get_setting("language")
                        ),
                    },
                )
                # self.clear_cookie("user")
                # self.clear_cookie("user_data")
                return self.clear_cookie("token")
            # if we don't have a user
            if not user_data:
                auth_log.error(
                    f"User attempted to log into {entered_username}. Authentication"
                    f" failed from remote IP {self.get_remote_ip()}"
                    " User does not exist."
                )
                self.controller.log_attempt(self.get_remote_ip(), entered_username)
                self.finish_json(
                    403,
                    {
                        "status": "error",
                        "error": self.helper.translation.translate(
                            "login", "incorrect", self.helper.get_setting("language")
                        ),
                    },
                )
                # self.clear_cookie("user")
                # self.clear_cookie("user_data")
                return self.clear_cookie("token")

            # if they are disabled
            if not user_data.enabled:
                auth_log.error(
                    f"User attempted to log into {entered_username}. "
                    f"Authentication failed from remote IP {self.get_remote_ip()}."
                    " User account disabled"
                )
                self.controller.log_attempt(self.get_remote_ip(), entered_username)
                self.finish_json(
                    403,
                    {
                        "status": "error",
                        "error": self.helper.translation.translate(
                            "login", "disabled", self.helper.get_setting("language")
                        ),
                    },
                )
                # self.clear_cookie("user")
                # self.clear_cookie("user_data")
                return self.clear_cookie("token")
            login_result = self.helper.verify_pass(entered_password, user_data.password)

            # Valid Login
            if login_result:
                self.set_current_user(user_data.user_id)
                logger.info(
                    f"User: {user_data} Logged in from IP: {self.get_remote_ip()}"
                )
                if not user_data.last_ip and user_data.username == "admin":
                    self.controller.first_login = True
                # record this login
                user_data.last_ip = self.get_remote_ip()
                user_data.last_login = Helpers.get_time_as_string()
                user_data.save()
                auth_log.info(
                    f"{entered_username} successfully"
                    " authenticated and logged"
                    f" into panel from remote IP {self.get_remote_ip()}"
                )
                # log this login
                self.controller.management.add_to_audit_log(
                    user_data.user_id, "Logged in", None, self.get_remote_ip()
                )

                return self.finish_json(
                    200, {"status": "ok", "data": {"message": "login successful!"}}
                )

            # We'll continue on and handle unsuccessful logins
            auth_log.error(
                f"User attempted to log into {entered_username}."
                f" Authentication failed from remote IP {self.get_remote_ip()}"
            )
            self.controller.log_attempt(self.get_remote_ip(), entered_username)
            # self.clear_cookie("user")
            # self.clear_cookie("user_data")
            self.clear_cookie("token")
            error_msg = self.helper.translation.translate(
                "login", "incorrect", self.helper.get_setting("language")
            )
            if entered_password == "app/config/default-creds.txt":
                error_msg += ". "
                error_msg += self.helper.translation.translate(
                    "login", "defaultPath", self.helper.get_setting("language")
                )
            # log this failed login attempt
            self.controller.management.add_to_audit_log(
                user_data.user_id, "Tried to log in", None, self.get_remote_ip()
            )
            return self.finish_json(
                403,
                {
                    "status": "error",
                    "error": "INVALID CREDENTIALS",
                    "error_data": error_msg,
                },
            )
        else:
            self.redirect("/login?")

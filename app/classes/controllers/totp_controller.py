import re
import pyotp
from app.classes.shared.helpers import Helpers
from app.classes.models.users import HelperUsers
from app.classes.models.totp import HelperTOTP


class TOTPController:
    def __init__(self, totp_helper, helper):
        self.totp_helper = totp_helper
        self.helper = helper
        self.pending_totp = {}

    def create_user_totp(self, user_id: int) -> dict:
        user = HelperUsers.get_user(user_id)
        user_secret = pyotp.random_base32()
        totp_id = Helpers.create_uuid()
        self.pending_totp[totp_id] = {
            "id": totp_id,
            "totp_secret": user_secret,
            "user_id": user_id,
            "username": user["username"],
        }
        return self.pending_totp[totp_id]

    def delete_user_totp(self, totp_id: str) -> bool:
        return self.totp_helper.delete_totp_entry(totp_id)

    def validate_user_totp(self, user_id: int, totp_code: str) -> bool:
        """Check current code and user_id against all user totp codes until we find one
        that matches.

        Args:
            user_id (_type_): _description_
            totp_code (_type_): _description_

        Returns:
            _type_: _description_
        """
        user = HelperUsers.get_by_id(user_id)
        authenticated = False
        # Iterate through just in case a user has multiple 2FA methods
        for totp in user.totp_user:
            totp_factory = pyotp.TOTP(totp.totp_secret)
            if totp_factory.verify(
                totp_code,
                valid_window=int(self.helper.get_setting("enable_otp_skew", False)),
                # Casting boolean value as window. 1 for true :)
            ):
                authenticated = True
        return authenticated

    def verify_user_totp(
        self, user_id: int, totp_id: str, totp_name: str, totp_code: str
    ) -> dict:
        """Takes the desired totp_id and compares it against the pending totp requests.
        If we find a totp_id and matching user ID we verify the code we're recieving. If
        this is successful we add the entry to the database.

        Args:
            user_id (_type_): _description_
            totp_id (_type_): _description_
            totp_code (_type_): _description_

        Returns:
            _type_: _description_
        """
        if totp_id and int(self.pending_totp.get(totp_id)["user_id"]) == user_id:
            user = HelperUsers.get_by_id(user_id)
            totp_code = str(totp_code)  # Set totp to desired string
            totp_factory = pyotp.TOTP(self.pending_totp[totp_id]["totp_secret"])
            if totp_factory.verify(totp_code):
                return HelperTOTP.create_user_totp(
                    totp_id,
                    totp_name,
                    user,
                    self.pending_totp[totp_id]["totp_secret"],
                )
        return False

    def create_missing_backup_codes(self, user_id):
        user = HelperUsers.get_by_id(user_id)
        num_codes = 6 - len(list(user.recovery_user))
        hashed_codes = []
        plain_text_codes = []
        for i in range(num_codes):
            code = str(self.helper.random_string_generator(16))
            hashed_codes.append(self.helper.encode_pass(code.lower()))
            plain_text_codes.append(re.sub(r"(\w{4})(?=\w)", r"\1-", code).upper())
            i += 1
        self.totp_helper.add_recovery_codes(user, hashed_codes)
        return plain_text_codes

    def remove_recovery_code(self, user_id, recovery_code):
        if user_id != recovery_code.user.user_id:
            raise RuntimeError("Unable to verify user")
        self.totp_helper.remove_recovery_code(recovery_code.id)

    def remove_all_recovery_codes(self, user_id: int):
        self.totp_helper.remove_all_recovery_codes(user_id)

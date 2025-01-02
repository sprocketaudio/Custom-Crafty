import re
import pyotp
from app.classes.models.users import HelperUsers
from app.classes.models.totp import HelperTOTP


class TOTPController:
    def __init__(self, totp_helper, helper):
        self.totp_helper = totp_helper
        self.helper = helper

    @staticmethod
    def create_user_totp(name: str, user_id: int) -> str:
        user = HelperUsers.get_by_id(user_id)
        user_secret = pyotp.random_base32()
        return HelperTOTP.create_user_totp(name, user, user_secret)

    def delete_user_totp(self, totp_id: str) -> bool:
        return self.totp_helper.delete_totp_entry(totp_id)

    def verify_user_totp(self, user_id, totp_code):
        user = HelperUsers.get_by_id(user_id)
        authenticated = False
        # Iterate through just in case a user has multiple 2FA methods
        for totp in user.totp_user:
            totp_factory = pyotp.TOTP(totp.totp_secret)
            if totp_factory.verify(totp_code):
                authenticated = True
        return authenticated

    def create_missing_backup_codes(self, user_id):
        user = HelperUsers.get_by_id(user_id)
        num_codes = 6 - len(list(user.recovery_user))
        hashed_codes = []
        plain_text_codes = []
        for i in range(num_codes):
            code = str(self.helper.random_string_generator(16))
            hashed_codes.append(self.helper.encode_pass(code.lower()))
            plain_text_codes.append(re.sub(r"(\w{4})", r"\1-", code).upper())
            i += 1
        self.totp_helper.add_recovery_codes(user, hashed_codes)
        return plain_text_codes

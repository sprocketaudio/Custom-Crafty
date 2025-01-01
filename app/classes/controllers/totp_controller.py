import pyotp
from app.classes.models.users import HelperUsers
from app.classes.models.totp import HelperTOTP


class TOTPController:
    @staticmethod
    def create_user_totp(name: str, user_id: int):
        user = HelperUsers.get_by_id(user_id)
        user_secret = pyotp.random_base32()
        return HelperTOTP.create_user_totp(name, user, user_secret)

    @staticmethod
    def verify_user_totp(user_id, totp_code):
        user = HelperUsers.get_by_id(user_id)
        authenticated = False
        for totp in user.totp_user:
            totp_factory = pyotp.TOTP(totp.totp_secret)
            print(totp_factory.now())
            if totp_factory.verify(totp_code):
                authenticated = True
        return authenticated

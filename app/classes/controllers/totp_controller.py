import re
from datetime import timezone, datetime, timedelta
import logging
import pyotp
from app.classes.shared.helpers import Helpers
from app.classes.models.users import HelperUsers
from app.classes.models.totp import HelperTOTP

logger = logging.getLogger(__name__)


class TOTPController:
    def __init__(self, totp_helper, helper):
        self.totp_helper = totp_helper
        self.helper = helper
        self.pending_totp = {}
        self.used_totp_codes = {}

    def create_user_totp(self, user_id: int) -> dict:
        """Creates temporary user totp in self.pending_totp var until it is verified.

        Args:
            user_id (int): _description_

        Returns:
            dict: dictionary with id, secret, user_id, username, and iat
        """
        user = HelperUsers.get_user(user_id)
        user_secret = pyotp.random_base32()
        totp_id = Helpers.create_uuid()
        self.pending_totp[totp_id] = {
            "id": totp_id,
            "totp_secret": user_secret,
            "user_id": user_id,
            "username": user["username"],
            "iat": datetime.now(tz=timezone.utc),
        }
        logger.info("Created pending MFA for user %s", user_id)
        return self.pending_totp[totp_id]

    def delete_user_totp(self, totp_id: str) -> bool:
        """Calls helper function to remove requested totp method from the database.

        Args:
            totp_id (str): _description_

        Returns:
            bool: _description_
        """
        logger.info("Deleted MFA entry with ID %s", totp_id)
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
        now = datetime.now(tz=timezone.utc)

        # Check to see if someone is trying to reuse a key in the 60 second window
        if str(user_id) in self.used_totp_codes:
            if str(totp_code) in self.used_totp_codes[str(user_id)]:
                if now - self.used_totp_codes[str(user_id)][totp_code] < timedelta(
                    seconds=60
                ):
                    logger.info(
                        "Someone is attempting to reuse MFA code for user %s", user_id
                    )
                    return authenticated
        else:
            self.used_totp_codes[str(user_id)] = {}  # Init empty dict if not in there

        # Store OTP as used for 60 seconds
        self.used_totp_codes[str(user_id)][str(totp_code)] = now

        # Clean up expired entries reclaim some memory
        for key in list(self.used_totp_codes.keys()):
            for item in list(self.used_totp_codes[key].keys()):
                if now - self.used_totp_codes[key][item] > timedelta(seconds=60):
                    del self.used_totp_codes[key][item]

        for totp in user.totp_user:
            totp_factory = pyotp.TOTP(totp.totp_secret)
            if totp_factory.verify(
                totp_code,
                valid_window=int(self.helper.get_setting("enable_otp_skew", False)),
                # Casting boolean value as window. 1 for true :)
            ):
                logger.info("Successfully verified user MFA %s", user_id)
                authenticated = True
        return authenticated

    def verify_user_totp(
        self, user_id: int, totp_id: str, totp_name: str, totp_code: str
    ):
        """Takes the desired totp_id and compares it against the pending totp requests.
        If we find a totp_id and matching user ID we verify the code we're recieving. If
        this is successful we add the entry to the database.

        Args:
            user_id (int): _description_
            totp_id (str): _description_
            totp_code (str): _description_

        Returns:
            model: totp model
        """
        if totp_id and int(self.pending_totp.get(totp_id)["user_id"]) == user_id:
            user = HelperUsers.get_by_id(user_id)
            totp_code = str(totp_code)  # Set totp to desired string
            totp_factory = pyotp.TOTP(self.pending_totp[totp_id]["totp_secret"])
            if totp_factory.verify(totp_code):
                user_totp = HelperTOTP.create_user_totp(
                    totp_id,
                    totp_name,
                    user,
                    self.pending_totp[totp_id]["totp_secret"],
                )
                self.pending_totp.pop(totp_id)
                logger.info("Successfully created and added user MFA %s", user_id)
                return user_totp
        return False

    def create_missing_backup_codes(self, user_id: int):
        """Does math to determine how many new backup codes should be created.
        This is called on the validation of a new TOTP method. This returns the codes
        or a boolean value. This also calls a helper function to send the codes to the
        database as hashed/salted values.

        Args:
            user_id (int): _description_

        Returns:
            _type_: list/bool
        """
        user = HelperUsers.get_by_id(user_id)
        num_codes = 6 - len(list(user.recovery_user))
        logger.info("Found user needs %s backup codes. Creating them", num_codes)
        hashed_codes = []
        plain_text_codes = []
        for _ in range(num_codes):
            code = str(self.helper.random_string_generator(16))
            hashed_codes.append(self.helper.encode_pass(code.lower()))
            plain_text_codes.append(re.sub(r"(\w{4})(?=\w)", r"\1-", code).upper())
        self.totp_helper.add_recovery_codes(user, hashed_codes)
        return plain_text_codes

    def remove_recovery_code(self, user_id: int, recovery_code: str):
        """Calls helper function to remove specific backup code from DB.
        This is generally after a user has burned their recovery code on login.

        Args:
            user_id (int): _description_
            recovery_code (str): _description_

        Raises:
            RuntimeError: _description_
        """
        if user_id != recovery_code.user.user_id:
            raise RuntimeError("Unable to verify user")
        self.totp_helper.remove_recovery_code(recovery_code.id)

    def remove_all_recovery_codes(self, user_id: int):
        """Calls helper function to remove all recovery codes for user from DB

        Args:
            user_id (int): _description_
        """
        self.totp_helper.remove_all_recovery_codes(user_id)

    def purge_pending(self):
        """Purge pending totp methods from dict that have not been completed after 60
        minutes. This runs on a schedule every 24 hours from tasks.py
        """
        logger.info("Checking and purging stale pending MFA")
        for totp_id in list(self.pending_totp.keys()):
            if datetime.now(tz=timezone.utc) - self.pending_totp[totp_id][
                "iat"
            ] > timedelta(minutes=60):
                del self.pending_totp[totp_id]  # Safe deletion
                logger.info(f"Deleted expired entry {totp_id}")

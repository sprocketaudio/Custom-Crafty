import logging
import datetime
import typing as t

from peewee import (
    ForeignKeyField,
    CharField,
    AutoField,
    IntegerField,
    DateTimeField,
    BooleanField,
    CompositeKey,
    DoesNotExist,
    JOIN,
)

from app.classes.shared.helpers import Helpers
from app.classes.models.users import Users
from app.classes.models.base_model import BaseModel

logger = logging.getLogger(__name__)


class TOTPData(BaseModel):
    """Model for user TOTP methods.

    Consists of:
    UUID PK
    Foreign key user ID
    totp secret

    Args:
        BaseModel (_type_): _description_
    """

    entry = CharField(primary_key=True, default=Helpers.create_uuid())
    name = CharField(default="TOTP")
    user = ForeignKeyField(Users, backref="totp_user")
    totp_secret = CharField()

    class Meta:
        table_name = "totp_data"


class TOTPRecovery(BaseModel):
    """Model for user TOTP recovery.
    Consists of:
    UUID PK
    user_id foreign key field
    the recovery secret

    We will try to limit users to only 6 backup codes.

    Args:
        BaseModel (_type_): _description_
    """

    entry = CharField(primary_key=True, default=Helpers.create_uuid())
    user = ForeignKeyField(Users, backref="recovery_user")
    recovery_secret = CharField()

    class Meta:
        table_name = "totp_recovery"


class HelperTOTP:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def create_user_totp(name: str, user: Users, user_secret: str) -> str:
        totp_id = TOTPData.create(name=name, user=user, totp_secret=user_secret)
        return totp_id

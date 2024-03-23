import datetime
import uuid
import peewee
import logging

from app.classes.shared.console import Console
from app.classes.shared.migration import Migrator, MigrateHistory
from app.classes.models.management import (
    AuditLog,
    Webhooks,
    Schedules,
    Backups,
)
from app.classes.models.server_permissions import RoleServers
from app.classes.models.servers import Servers

logger = logging.getLogger(__name__)


def migrate(migrator: Migrator, database, **kwargs):
    """
    Write your migrations here.
    """
    db = database

    try:
        # Changes on Server Table
        migrator.alter_column_type(
            Servers,
            "server_id",
            peewee.CharField(primary_key=True, default=str(uuid.uuid4())),
        )

        # Changes on Audit Log Table
        migrator.alter_column_type(
            AuditLog,
            "server_id",
            peewee.ForeignKeyField(
                Servers,
                backref="audit_server",
                null=True,
                field=peewee.CharField(primary_key=True, default=str(uuid.uuid4())),
            ),
        )
        # Changes on Webhook Table
        migrator.alter_column_type(
            Webhooks,
            "server_id",
            peewee.ForeignKeyField(
                Servers,
                backref="webhook_server",
                null=True,
                field=peewee.CharField(primary_key=True, default=str(uuid.uuid4())),
            ),
        )

    except Exception as ex:
        logger.error("Error while migrating Data from Int to UUID (Type Change)")
        logger.error(ex)
        Console.error("Error while migrating Data from Int to UUID (Type Change)")
        Console.error(ex)
        last_migration = MigrateHistory.get_by_id(MigrateHistory.select().count())
        last_migration.delete()
        return

    return


def rollback(migrator: Migrator, database, **kwargs):
    """
    Write your rollback migrations here.
    """
    db = database

    # Changes on Server Table
    migrator.alter_column_type(
        "servers",
        "server_id",
        peewee.AutoField(),
    )

    # Changes on Audit Log Table
    migrator.alter_column_type(
        AuditLog,
        "server_id",
        peewee.IntegerField(default=None, index=True),
    )

    # Changes on Webhook Table
    migrator.alter_column_type(
        Webhooks,
        "server_id",
        peewee.IntegerField(null=True),
    )

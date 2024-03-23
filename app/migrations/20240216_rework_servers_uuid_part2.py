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

logger = logging.getLogger(__name__)


def migrate(migrator: Migrator, database, **kwargs):
    """
    Write your migrations here.
    """
    db = database

    this_migration = MigrateHistory.get(MigrateHistory.name == "20240216_rework_servers_uuid_part2")
    if this_migration:
        Console.debug("Update database already done, skipping this migration")
        return
    else :
        Console.debug("Update database not done, doing : Migration Data from Int to UUID")

    # **********************************************************************************
    #          Servers New Model from Old (easier to migrate without dunmping Database)
    # **********************************************************************************
    class Servers(peewee.Model):
        server_id = peewee.CharField(primary_key=True, default=str(uuid.uuid4()))
        created = peewee.DateTimeField(default=datetime.datetime.now)
        server_uuid = peewee.CharField(default="", index=True)
        server_name = peewee.CharField(default="Server", index=True)
        path = peewee.CharField(default="")
        backup_path = peewee.CharField(default="")
        executable = peewee.CharField(default="")
        log_path = peewee.CharField(default="")
        execution_command = peewee.CharField(default="")
        auto_start = peewee.BooleanField(default=0)
        auto_start_delay = peewee.IntegerField(default=10)
        crash_detection = peewee.BooleanField(default=0)
        stop_command = peewee.CharField(default="stop")
        executable_update_url = peewee.CharField(default="")
        server_ip = peewee.CharField(default="127.0.0.1")
        server_port = peewee.IntegerField(default=25565)
        logs_delete_after = peewee.IntegerField(default=0)
        type = peewee.CharField(default="minecraft-java")
        show_status = peewee.BooleanField(default=1)
        created_by = peewee.IntegerField(default=-100)
        shutdown_timeout = peewee.IntegerField(default=60)
        ignored_exits = peewee.CharField(default="0")

        class Meta:
            table_name = "servers"
            database = db

    try:
        logger.info("Migrating Data from Int to UUID (Foreign Keys)")
        Console.info("Migrating Data from Int to UUID (Foreign Keys)")
        # Changes on Audit Log Table
        for audit_log in AuditLog.select():
            old_server_id = audit_log.server_id_id
            if old_server_id == "0" or old_server_id is None:
                server_uuid = None
            else:
                try:
                    server = Servers.get_by_id(old_server_id)
                    server_uuid = server.server_uuid
                except:
                    server_uuid = old_server_id
            AuditLog.update(server_id=server_uuid).where(
                AuditLog.audit_id == audit_log.audit_id
            ).execute()

        # Changes on Webhooks Log Table
        for webhook in Webhooks.select():
            old_server_id = webhook.server_id_id
            try:
                server = Servers.get_by_id(old_server_id)
                server_uuid = server.server_uuid
            except:
                server_uuid = old_server_id
            Webhooks.update(server_id=server_uuid).where(
                Webhooks.id == webhook.id
            ).execute()

        # Changes on Schedules Log Table
        for schedule in Schedules.select():
            old_server_id = schedule.server_id_id
            try:
                server = Servers.get_by_id(old_server_id)
                server_uuid = server.server_uuid
            except:
                server_uuid = old_server_id
            Schedules.update(server_id=server_uuid).where(
                Schedules.schedule_id == schedule.schedule_id
            ).execute()

        # Changes on Backups Log Table
        for backup in Backups.select():
            old_server_id = backup.server_id_id
            try:
                server = Servers.get_by_id(old_server_id)
                server_uuid = server.server_uuid
            except:
                server_uuid = old_server_id
            Backups.update(server_id=server_uuid).where(
                Backups.server_id == old_server_id
            ).execute()

        # Changes on RoleServers Log Table
        for role_servers in RoleServers.select():
            old_server_id = role_servers.server_id_id
            try:
                server = Servers.get_by_id(old_server_id)
                server_uuid = server.server_uuid
            except:
                server_uuid = old_server_id
            RoleServers.update(server_id=server_uuid).where(
                RoleServers.role_id == role_servers.id
                and RoleServers.server_id == old_server_id
            ).execute()

        logger.info("Migrating Data from Int to UUID (Foreign Keys) : SUCCESS")
        Console.info("Migrating Data from Int to UUID (Foreign Keys) : SUCCESS")

    except Exception as ex:
        logger.error("Error while migrating Data from Int to UUID (Foreign Keys)")
        logger.error(ex)
        Console.error("Error while migrating Data from Int to UUID (Foreign Keys)")
        Console.error(ex)
        last_migration = MigrateHistory.get_by_id(MigrateHistory.select().count())
        last_migration.delete()
        return

    try:
        logger.info("Migrating Data from Int to UUID (Primary Keys)")
        Console.info("Migrating Data from Int to UUID (Primary Keys)")
        # Migrating servers from the old id type to the new one
        for server in Servers.select():
            Servers.update(server_id=server.server_uuid).where(
                Servers.server_id == server.server_id
            ).execute()

        logger.info("Migrating Data from Int to UUID (Primary Keys) : SUCCESS")
        Console.info("Migrating Data from Int to UUID (Primary Keys) : SUCCESS")

    except Exception as ex:
        logger.error("Error while migrating Data from Int to UUID (Primary Keys)")
        logger.error(ex)
        Console.error("Error while migrating Data from Int to UUID (Primary Keys)")
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

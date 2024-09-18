import logging
import json
import os
from apscheduler.jobstores.base import JobLookupError
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from app.classes.models.server_permissions import EnumPermissionsServer
from app.classes.shared.file_helpers import FileHelpers
from app.classes.web.base_api_handler import BaseApiHandler
from app.classes.shared.helpers import Helpers

logger = logging.getLogger(__name__)

BACKUP_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "minLength": 5,
            "error": "typeString",
            "fill": True,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}
BACKUP_PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "backup_name": {
            "type": "string",
            "minLength": 3,
            "error": "backupName",
        },
        "backup_location": {
            "type": "string",
            "minLength": 1,
            "error": "typeString",
            "fill": True,
        },
        "max_backups": {
            "type": "integer",
            "error": "typeInteger",
            "fill": True,
        },
        "compress": {
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
        "shutdown": {
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
        "before": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "after": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "excluded_dirs": {
            "type": "array",
            "error": "typeList",
            "fill": True,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}

BASIC_BACKUP_PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "backup_name": {"type": "string", "minLength": 3, "error": "backupName"},
        "max_backups": {
            "type": "integer",
            "error": "typeInteger",
            "fill": True,
        },
        "compress": {
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
        "shutdown": {
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
        "before": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "after": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "excluded_dirs": {
            "type": "array",
            "error": "typeList",
            "fill": True,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}
ID_MISMATCH = "Server ID backup server ID different"
GENERAL_AUTH_ERROR = "Authorization Error"


class ApiServersServerBackupsBackupIndexHandler(BaseApiHandler):
    def get(self, server_id: str, backup_id: str):
        auth_data = self.authenticate_user()
        backup_conf = self.controller.management.get_backup_config(backup_id)
        if not auth_data:
            return
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        if backup_conf["server_id"]["server_id"] != server_id:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "ID_MISMATCH",
                    "error_data": ID_MISMATCH,
                },
            )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.BACKUP not in server_permissions:
            # if the user doesn't have Schedule permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": GENERAL_AUTH_ERROR,
                },
            )
        self.finish_json(200, backup_conf)

    def delete(self, server_id: str, backup_id: str):
        auth_data = self.authenticate_user()
        backup_conf = self.controller.management.get_backup_config(backup_id)
        if backup_conf["server_id"]["server_id"] != server_id:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "ID_MISMATCH",
                    "error_data": ID_MISMATCH,
                },
            )
        if not auth_data:
            return
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.BACKUP not in server_permissions:
            # if the user doesn't have Schedule permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": GENERAL_AUTH_ERROR,
                },
            )

        self.controller.management.add_to_audit_log(
            auth_data[4]["user_id"],
            f"Edited server {server_id}: removed backup config"
            f" {backup_conf['backup_name']}",
            server_id,
            self.get_remote_ip(),
        )
        if backup_conf["default"]:
            return self.finish_json(
                405,
                {
                    "status": "error",
                    "error": "NOT_ALLOWED",
                    "error_data": "Cannot delete default backup",
                },
            )
        self.controller.management.delete_backup_config(backup_id)

        return self.finish_json(200, {"status": "ok"})

    def post(self, server_id: str, backup_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.BACKUP not in server_permissions:
            # if the user doesn't have Schedule permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": GENERAL_AUTH_ERROR,
                },
            )
        backup_config = self.controller.management.get_backup_config(backup_id)
        if backup_config["server_id"]["server_id"] != server_id:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "ID_MISMATCH",
                    "error_data": ID_MISMATCH,
                },
            )

        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )
        try:
            validate(data, BACKUP_SCHEMA)
        except ValidationError as why:
            offending_key = ""
            if why.schema.get("fill", None):
                offending_key = why.path[0] if why.path else None
            err = f"""{offending_key} {self.translator.translate(
                "validators",
                why.schema.get("error"),
                self.controller.users.get_user_lang_by_id(auth_data[4]["user_id"]),
            )} {why.schema.get("enum", "")}"""
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_JSON_SCHEMA",
                    "error_data": f"{str(err)}",
                },
            )

        svr_obj = self.controller.servers.get_server_obj(server_id)
        server_data = self.controller.servers.get_server_data_by_id(server_id)
        zip_name = data["filename"]
        # import the server again based on zipfile
        backup_config = self.controller.management.get_backup_config(backup_id)
        backup_location = os.path.join(
            backup_config["backup_location"], backup_config["backup_id"]
        )
        if Helpers.validate_traversal(backup_location, zip_name):
            try:
                temp_dir = Helpers.unzip_backup_archive(backup_location, zip_name)
            except (FileNotFoundError, NotADirectoryError) as e:
                return self.finish_json(
                    400,
                    {"status": "error", "error": "NO BACKUP FOUND", "error_data": e},
                )
            if server_data["type"] == "minecraft-java":
                new_server = self.controller.restore_java_zip_server(
                    svr_obj.server_name,
                    temp_dir,
                    server_data["executable"],
                    "1",
                    "2",
                    server_data["server_port"],
                    server_data["created_by"],
                )
            elif server_data["type"] == "minecraft-bedrock":
                new_server = self.controller.restore_bedrock_zip_server(
                    svr_obj.server_name,
                    temp_dir,
                    server_data["executable"],
                    server_data["server_port"],
                    server_data["created_by"],
                )
            new_server_id = new_server
            new_server = self.controller.servers.get_server_data(new_server)
            self.controller.rename_backup_dir(
                server_id,
                new_server_id,
                new_server["server_id"],
            )
            # preserve current schedules
            for schedule in self.controller.management.get_schedules_by_server(
                server_id
            ):
                job_data = self.controller.management.get_scheduled_task(
                    schedule.schedule_id
                )
                job_data["server_id"] = new_server_id
                del job_data["schedule_id"]
                self.tasks_manager.update_job(schedule.schedule_id, job_data)
            # preserve execution command
            new_server_obj = self.controller.servers.get_server_obj(new_server_id)
            new_server_obj.execution_command = server_data["execution_command"]
            # reset executable path
            if svr_obj.path in svr_obj.executable:
                new_server_obj.executable = str(svr_obj.executable).replace(
                    svr_obj.path, new_server_obj.path
                )
            # reset run command path
            if svr_obj.path in svr_obj.execution_command:
                new_server_obj.execution_command = str(
                    svr_obj.execution_command
                ).replace(svr_obj.path, new_server_obj.path)
            # reset log path
            if svr_obj.path in svr_obj.log_path:
                new_server_obj.log_path = str(svr_obj.log_path).replace(
                    svr_obj.path, new_server_obj.path
                )
            self.controller.servers.update_server(new_server_obj)

            # preserve backup config
            server_backups = self.controller.management.get_backups_by_server(server_id)
            for backup in server_backups:
                old_backup_id = server_backups[backup]["backup_id"]
                del server_backups[backup]["backup_id"]
                server_backups[backup]["server_id"] = new_server_id
                if str(server_id) in (server_backups[backup]["backup_location"]):
                    server_backups[backup]["backup_location"] = str(
                        server_backups[backup]["backup_location"]
                    ).replace(str(server_id), str(new_server_id))
                new_backup_id = self.controller.management.add_backup_config(
                    server_backups[backup]
                )
                os.listdir(server_backups[backup]["backup_location"])
                FileHelpers.move_dir(
                    os.path.join(
                        server_backups[backup]["backup_location"], old_backup_id
                    ),
                    os.path.join(
                        server_backups[backup]["backup_location"], new_backup_id
                    ),
                )
            # remove old server's tasks
            try:
                self.tasks_manager.remove_all_server_tasks(server_id)
            except JobLookupError as e:
                logger.info("No active tasks found for server: {e}")
            self.controller.remove_server(server_id, True)

        self.controller.management.add_to_audit_log(
            auth_data[4]["user_id"],
            f"Restored server {server_id} backup {data['filename']}",
            server_id,
            self.get_remote_ip(),
        )

        return self.finish_json(200, {"status": "ok"})

    def patch(self, server_id: str, backup_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )

        try:
            if auth_data[4]["superuser"]:
                validate(data, BACKUP_PATCH_SCHEMA)
            else:
                validate(data, BASIC_BACKUP_PATCH_SCHEMA)
        except ValidationError as why:
            offending_key = ""
            if why.schema.get("fill", None):
                offending_key = why.path[0] if why.path else None
            err = f"""{offending_key} {self.translator.translate(
                "validators",
                why.schema.get("error"),
                self.controller.users.get_user_lang_by_id(auth_data[4]["user_id"]),
            )} {why.schema.get("enum", "")}"""
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_JSON_SCHEMA",
                    "error_data": f"{str(err)}",
                },
            )
        backup_conf = self.controller.management.get_backup_config(backup_id)
        if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
            # if the user doesn't have access to the server, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": GENERAL_AUTH_ERROR,
                },
            )
        if backup_conf["server_id"]["server_id"] != server_id:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "ID_MISMATCH",
                    "error_data": ID_MISMATCH,
                },
            )
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.BACKUP not in server_permissions:
            # if the user doesn't have Schedule permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": GENERAL_AUTH_ERROR,
                },
            )
        self.controller.management.update_backup_config(backup_id, data)
        return self.finish_json(200, {"status": "ok"})


class ApiServersServerBackupsBackupFilesIndexHandler(BaseApiHandler):
    def delete(self, server_id: str, backup_id: str):
        auth_data = self.authenticate_user()
        backup_conf = self.controller.management.get_backup_config(backup_id)
        if backup_conf["server_id"]["server_id"] != server_id:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "ID_MISMATCH",
                    "error_data": ID_MISMATCH,
                },
            )
        if not auth_data:
            return
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.BACKUP not in server_permissions:
            # if the user doesn't have Schedule permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": GENERAL_AUTH_ERROR,
                },
            )

        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )
        try:
            validate(data, BACKUP_SCHEMA)
        except ValidationError as why:
            offending_key = ""
            if why.schema.get("fill", None):
                offending_key = why.path[0] if why.path else None
            err = f"""{offending_key} {self.translator.translate(
                "validators",
                why.schema.get("error"),
                self.controller.users.get_user_lang_by_id(auth_data[4]["user_id"]),
            )} {why.schema.get("enum", "")}"""
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_JSON_SCHEMA",
                    "error_data": f"{str(err)}",
                },
            )
        self.helper.validate_traversal(
            os.path.join(backup_conf["backup_location"], backup_conf["backup_id"]),
            os.path.join(
                backup_conf["backup_location"],
                backup_conf["backup_id"],
                data["filename"],
            ),
        )
        try:
            FileHelpers.del_file(
                os.path.join(
                    backup_conf["backup_location"],
                    backup_conf["backup_id"],
                    data["filename"],
                )
            )
        except Exception as e:
            return self.finish_json(
                400, {"status": "error", "error": "DELETE FAILED", "error_data": e}
            )
        self.controller.management.add_to_audit_log(
            auth_data[4]["user_id"],
            f"Edited server {server_id}: removed backup {data['filename']}",
            server_id,
            self.get_remote_ip(),
        )

        return self.finish_json(200, {"status": "ok"})

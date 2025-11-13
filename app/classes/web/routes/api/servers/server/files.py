import os
import logging
import json
import html
import threading
from shutil import Error as shutilError
from datetime import datetime
from pathlib import Path, PurePath
from jsonschema import validate
from jsonschema.exceptions import ValidationError

from app.classes.models.server_permissions import EnumPermissionsServer
from app.classes.helpers.helpers import Helpers
from app.classes.helpers.file_helpers import FileHelpers
from app.classes.web.base_api_handler import BaseApiHandler

logger = logging.getLogger(__name__)

files_get_schema = {
    "type": "object",
    "properties": {
        "page": {
            "type": "string",
            "minLength": 1,
            "error": "typeString",
            "fill": True,
        },
        "path": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}

files_patch_schema = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "contents": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}

files_unzip_schema = {
    "type": "object",
    "properties": {
        "folder": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "proc_id": {
            "type": "string",
            "desc": "uuid",
            "error": "typeString",
            "fill": True,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}

files_operation_schema = {
    "type": "object",
    "properties": {
        "source_path": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "target_path": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}

files_create_schema = {
    "type": "object",
    "properties": {
        "parent": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "name": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "directory": {
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}

files_rename_schema = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "new_name": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}

file_delete_schema = {
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}


class ApiServersServerFilesIndexHandler(BaseApiHandler):
    def post(self, server_id: str, backup_id=None):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
            # if the user doesn't have access to the server, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if (
            EnumPermissionsServer.FILES not in server_permissions
            and EnumPermissionsServer.BACKUP not in server_permissions
        ):
            # if the user doesn't have Files or Backup permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )

        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )
        try:
            validate(data, files_get_schema)
        except ValidationError as e:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_JSON_SCHEMA",
                    "error_data": str(e),
                },
            )
        # Check for absolute or relative path. Absolute paths should be deprecated
        request_path = data["path"]
        server_path = self.controller.servers.get_server_data_by_id(server_id)["path"]
        data["path"] = self.file_helper.get_absolute_path(
            server_path, server_id, data["path"]
        )
        if not Helpers.validate_traversal(
            server_path,
            data["path"],
        ):
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "TRAVERSAL DETECTED",
                    "error_data": str(e),
                },
            )
        if os.path.isdir(data["path"]):
            # TODO: limit some columns for specific permissions?
            folder = data["path"]
            return_json = {
                "root_path": {
                    "local_path": request_path,
                    "path": folder,
                    "top": data["path"]
                    == self.controller.servers.get_server_data_by_id(server_id)["path"],
                }
            }

            dir_list = []
            unsorted_files = []
            file_list = os.listdir(folder)
            for item in file_list:
                if os.path.isdir(os.path.join(folder, item)):
                    dir_list.append(item)
                else:
                    unsorted_files.append(item)
            file_list = sorted(dir_list, key=str.casefold) + sorted(
                unsorted_files, key=str.casefold
            )
            for raw_filename in file_list:
                filename = html.escape(raw_filename)
                rel = os.path.join(folder, raw_filename)
                dpath = os.path.join(folder, filename)
                can_open, mime = self.file_helper.probably_can_open_file(dpath)
                modified_time = datetime.fromtimestamp(Path(dpath).stat().st_mtime)
                if backup_id:
                    if str(
                        dpath
                    ) in self.controller.management.get_excluded_backup_dirs(backup_id):
                        if os.path.isdir(rel):
                            return_json[filename] = {
                                "path": dpath,
                                "dir": True,
                                "excluded": True,
                            }
                        else:
                            try:
                                file_size = os.path.getsize(rel)
                            except (OSError, IOError):
                                file_size = 0
                            return_json[filename] = {
                                "path": dpath,
                                "dir": False,
                                "excluded": True,
                                "size": Helpers.human_readable_file_size(file_size),
                            }
                    else:
                        if os.path.isdir(rel):
                            return_json[filename] = {
                                "path": dpath,
                                "dir": True,
                                "excluded": False,
                            }
                        else:
                            try:
                                file_size = os.path.getsize(rel)
                            except (OSError, IOError):
                                file_size = 0
                            return_json[filename] = {
                                "path": dpath,
                                "dir": False,
                                "excluded": False,
                                "size": Helpers.human_readable_file_size(file_size),
                            }
                else:
                    if os.path.isdir(rel):
                        return_json[filename] = {
                            "path": str(
                                PurePath.relative_to(
                                    PurePath(dpath), PurePath(server_path)
                                )
                            ),
                            "dir": True,
                            "excluded": False,
                            "modified": modified_time.strftime("%Y/%m/%d %H:%M"),
                        }
                    else:
                        try:
                            file_size = os.path.getsize(rel)
                        except (OSError, IOError):
                            file_size = 0
                        return_json[filename] = {
                            "path": str(
                                PurePath.relative_to(
                                    PurePath(dpath), PurePath(server_path)
                                )
                            ),
                            "dir": False,
                            "excluded": False,
                            "can_open": can_open,
                            "mime": mime,
                            "modified": modified_time.strftime("%Y/%m/%d %H:%M"),
                            "size": Helpers.human_readable_file_size(file_size),
                        }
            self.finish_json(200, {"status": "ok", "data": return_json})
        else:
            try:
                if Path(data["path"]).is_file():
                    with open(data["path"], encoding="utf-8") as file:
                        file_contents = file.read()
                else:
                    raise OSError("Item is not a valid File")
            except (UnicodeDecodeError, OSError) as ex:
                self.finish_json(
                    400,
                    {"status": "error", "error": "DECODE_ERROR", "error_data": str(ex)},
                )
            self.finish_json(200, {"status": "ok", "data": file_contents})

    def delete(self, server_id: str, _backup_id=None):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
            # if the user doesn't have access to the server, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.FILES not in server_permissions:
            # if the user doesn't have Files permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )
        try:
            validate(data, file_delete_schema)
        except ValidationError as why:
            offending_key = ""
            if why.schema.get("fill", None):
                offending_key = why.path[0] if why.path else None
            err = f"""{offending_key} {self.translator.translate(
                "validators",
                why.schema.get("error", "additionalProperties"),
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
        # Check for absolute or relative path. Absolute paths should be deprecated
        server_path = self.controller.servers.get_server_data_by_id(server_id)["path"]
        data["filename"] = self.file_helper.get_absolute_path(
            server_path, server_id, data["filename"]
        )
        if (
            not Helpers.validate_traversal(
                self.controller.servers.get_server_data_by_id(server_id)["path"],
                data["filename"],
            )
            or data["filename"] == server_path
        ):
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "TRAVERSAL DETECTED",
                    "error_data": str("Traversal"),
                },
            )
        if os.path.isdir(data["filename"]):
            proc = FileHelpers.del_dirs(data["filename"])
        else:
            proc = FileHelpers.del_file(data["filename"])
        # disabling pylint because return value could be truthy
        # but not a true boolean value
        if proc == True:  # pylint: disable=singleton-comparison
            self.controller.management.add_to_audit_log(
                auth_data[4]["user_id"],
                f"Deleted item {data['filename']}",
                server_id,
                self.request.remote_ip,
            )
            return self.finish_json(200, {"status": "ok"})
        return self.finish_json(
            500, {"status": "error", "error": "SERVER RUNNING", "error_data": str(proc)}
        )

    def patch(self, server_id: str, _backup_id):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
            # if the user doesn't have access to the server, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.FILES not in server_permissions:
            # if the user doesn't have Files permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )
        try:
            validate(data, files_patch_schema)
        except ValidationError as why:
            offending_key = ""
            if why.schema.get("fill", None):
                offending_key = why.path[0] if why.path else None
            err = f"""{offending_key} {self.translator.translate(
                "validators",
                why.schema.get("error", "additionalProperties"),
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
        # Check for absolute or relative path. Absolute paths should be deprecated
        server_path = self.controller.servers.get_server_data_by_id(server_id)["path"]
        data["path"] = self.file_helper.get_absolute_path(
            server_path, server_id, data["path"]
        )
        if not Helpers.validate_traversal(
            self.controller.servers.get_server_data_by_id(server_id)["path"],
            data["path"],
        ):
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "TRAVERSAL DETECTED",
                    "error_data": str(e),
                },
            )
        file_path = Helpers.get_os_understandable_path(data["path"])
        file_contents = data["contents"]
        # Open the file in write mode and store the content in file_object
        with open(file_path, "w", encoding="utf-8") as file_object:
            file_object.write(file_contents)
        return self.finish_json(200, {"status": "ok"})

    def put(self, server_id: str, _backup_id):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
            # if the user doesn't have access to the server, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.FILES not in server_permissions:
            # if the user doesn't have Files permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )
        try:
            validate(data, files_create_schema)
        except ValidationError as why:
            offending_key = ""
            if why.schema.get("fill", None):
                offending_key = why.path[0] if why.path else None
            err = f"""{offending_key} {self.translator.translate(
                "validators",
                why.schema.get("error", "additionalProperties"),
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
        # Check for absolute or relative path. Absolute paths should be deprecated
        server_path = self.controller.servers.get_server_data_by_id(server_id)["path"]
        data["parent"] = self.file_helper.get_absolute_path(
            server_path, server_id, data["parent"]
        )
        path = os.path.join(data["parent"], data["name"])
        if not Helpers.validate_traversal(
            self.controller.servers.get_server_data_by_id(server_id)["path"],
            path,
        ):
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "TRAVERSAL DETECTED",
                    "error_data": str(e),
                },
            )
        if Helpers.check_path_exists(os.path.abspath(path)):
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "FILE EXISTS",
                    "error_data": str(e),
                },
            )
        if data["directory"]:
            os.mkdir(path)
        else:
            # Create the file by opening it
            with open(path, "w", encoding="utf-8") as file_object:
                file_object.close()
        return self.finish_json(200, {"status": "ok"})


class ApiServersServerFilesCreateHandler(BaseApiHandler):
    def patch(self, server_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
            # if the user doesn't have access to the server, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.FILES not in server_permissions:
            # if the user doesn't have Files permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )
        try:
            validate(data, files_rename_schema)
        except ValidationError as why:
            offending_key = ""
            if why.schema.get("fill", None):
                offending_key = why.path[0] if why.path else None
            err = f"""{offending_key} {self.translator.translate(
                "validators",
                why.schema.get("error", "additionalProperties"),
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
        # Check for absolute or relative path. Absolute paths should be deprecated
        server_path = self.controller.servers.get_server_data_by_id(server_id)["path"]
        path = self.file_helper.get_absolute_path(server_path, server_id, data["path"])
        new_item_name = data["new_name"]
        new_item_path = os.path.join(os.path.split(path)[0], new_item_name)
        if not Helpers.validate_traversal(
            self.controller.servers.get_server_data_by_id(server_id)["path"],
            path,
        ) or not Helpers.validate_traversal(
            self.controller.servers.get_server_data_by_id(server_id)["path"],
            new_item_path,
        ):
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "TRAVERSAL DETECTED",
                    "error_data": str(e),
                },
            )
        if Helpers.check_path_exists(os.path.abspath(new_item_path)):
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "FILE EXISTS",
                    "error_data": {},
                },
            )

        os.rename(path, new_item_path)
        return self.finish_json(200, {"status": "ok"})

    def put(self, server_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
            # if the user doesn't have access to the server, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.FILES not in server_permissions:
            # if the user doesn't have Files permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )
        try:
            validate(data, files_create_schema)
        except ValidationError as why:
            offending_key = ""
            if why.schema.get("fill", None):
                offending_key = why.path[0] if why.path else None
            err = f"""{offending_key} {self.translator.translate(
                "validators",
                why.schema.get("error", "additionalProperties"),
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
        # Check for absolute or relative path. Absolute paths should be deprecated
        server_path = self.controller.servers.get_server_data_by_id(server_id)["path"]
        file_path = self.file_helper.get_absolute_path(
            server_path, server_id, data["parent"]
        )
        path = os.path.join(file_path, data["name"])
        if not Helpers.validate_traversal(
            self.controller.servers.get_server_data_by_id(server_id)["path"],
            path,
        ):
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "TRAVERSAL DETECTED",
                    "error_data": str(e),
                },
            )
        if Helpers.check_path_exists(os.path.abspath(path)):
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "FILE EXISTS",
                    "error_data": "Item already exists in file tree",
                },
            )
        if data["directory"]:
            os.mkdir(path)
        else:
            # Create the file by opening it
            with open(path, "w", encoding="utf-8") as file_object:
                file_object.close()
        return self.finish_json(200, {"status": "ok"})


class ApiServersServerFilesZipHandler(BaseApiHandler):
    def post(self, server_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
            # if the user doesn't have access to the server, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.FILES not in server_permissions:
            # if the user doesn't have Files permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )
        try:
            validate(data, files_unzip_schema)
        except ValidationError as why:
            offending_key = ""
            if why.schema.get("fill", None):
                offending_key = why.path[0] if why.path else None
            err = f"""{offending_key} {self.translator.translate(
                "validators",
                why.schema.get("error", "additionalProperties"),
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

        # Check for absolute or relative path. Absolute paths should be deprecated
        server_path = self.controller.servers.get_server_data_by_id(server_id)["path"]
        target_file = self.file_helper.get_absolute_path(
            server_path, server_id, data["folder"]
        )
        user_id = auth_data[4]["user_id"]
        if not Helpers.validate_traversal(
            self.controller.servers.get_server_data_by_id(server_id)["path"],
            target_file,
        ):
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "TRAVERSAL DETECTED",
                    "error_data": str(e),
                },
            )
        if Helpers.check_file_exists(target_file):
            unzip_thread = threading.Thread(
                target=self.file_helper.unzip_file,
                daemon=True,
                args=(target_file, server_id),
                kwargs={"proc_id": data.get("proc_id")},
                name=f"{target_file}_unzip",
            )
            unzip_thread.start()
            self.controller.management.add_to_audit_log(
                auth_data[4]["user_id"],
                f"Unzipped file {target_file} in {data['folder']}",
                server_id,
                self.request.remote_ip,
            )
            return self.finish_json(200, {"status": "ok"})

        if user_id:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "FILE_DOES_NOT_EXIST",
                    "error_data": str(e),
                },
            )


class ApiServersServerFileDownload(BaseApiHandler):
    async def get(self, server_id: str, encoded_file_path: str):
        logger.debug(
            "Download file request received. server_id: %s, encoded file path: %s",
            server_id,
            encoded_file_path,
        )
        auth_data = self.authenticate_user()
        if not auth_data:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators",
                        "insufficientPerms",
                        self.helper.get_setting("language"),
                    ),
                },
            )

        filepath = html.unescape(encoded_file_path)
        # Check for absolute or relative path. Absolute paths should be deprecated
        server_path = self.controller.servers.get_server_data_by_id(server_id)["path"]
        file_path = Path(
            self.file_helper.get_absolute_path(server_path, server_id, filepath)
        )

        if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
            # if the user doesn't have access to the server, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.FILES not in server_permissions:
            # if the user doesn't have Files permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        try:
            if not Helpers.validate_traversal(
                self.controller.servers.get_server_data_by_id(server_id)["path"],
                file_path,
            ):
                return self.finish_json(
                    400,
                    {
                        "status": "error",
                        "error": "TRAVERSAL DETECTED",
                        "error_data": "TRAVERSAL DETECTED",
                    },
                )
        except ValueError:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "TRAVERSAL DETECTED",
                    "error_data": "TRAVERSAL DETECTED",
                },
            )

        if not file_path.exists():
            return self.finish_json(
                404,
                {
                    "status": "error",
                    "error": "File not found",
                    "error_data": f"Path does not exist: {file_path}",
                },
            )
        directory_download = False
        download_path = file_path
        if file_path.is_dir():
            directory_download = True
            logger.info("Requested download is a directory. Zipping...%s", file_path)
            archive_path = Path(
                self.controller.project_root,
                "temp",
                str(auth_data[4]["user_id"]),
                file_path.name,
            )
            archive_path.parent.mkdir(parents=True, exist_ok=True)

            target_total_size = self.file_helper.get_dir_size(Path(download_path))
            free_drive_storage = self.file_helper.get_drive_free_space(
                Path(download_path)
            )
            if not self.file_helper.has_enough_storage(
                target_total_size, free_drive_storage
            ):
                return self.finish_json(
                    507,
                    {
                        "status": "error",
                        "error": "Out Of Space",
                        "error_data": "System Does Not Have enough space for download",
                    },
                )
            self.file_helper.make_archive(archive_path, file_path)
            download_path = archive_path.with_suffix(".zip")

        self.controller.management.add_to_audit_log(
            auth_data[4]["user_id"],
            f"started file download for {download_path} from server {server_id}.",
            server_id,
            self.request.remote_ip,
        )
        await self.download_file(download_path)  # Make sure to check for permissions
        # and traversal before calling download. There is no permission checking
        # in this function
        if directory_download:
            os.remove(download_path)

        return None


class ApiServersServerFilesOperationHandler(BaseApiHandler):
    def move_or_copy(self, operation: str, target_file: Path, source_path: Path):
        if operation == "move":
            if Path(source_path).is_dir():
                try:
                    FileHelpers.move_dir(source_path, target_file)
                except shutilError as why:
                    raise shutilError from why
            else:
                try:
                    FileHelpers.move_file(source_path, target_file)
                except shutilError as why:
                    raise shutilError from why
        elif operation == "copy":
            if Path(source_path).is_dir():
                print(target_file)
                FileHelpers.copy_dir(source_path, target_file)
            else:
                FileHelpers.copy_file(source_path, target_file)

    def can_move_or_copy(self, target_path: Path, source_path: Path) -> tuple:
        if source_path == target_path:
            # Check if user is trying to copy to exactly where the file already is
            return (False, "sourceMatchTarget")

        if source_path in target_path.parents:
            # Check if user is trying  to copy directory into itself
            return (False, "targetInSource")

        return (True, "success")

    def post(self, server_id: str, operation: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
            # if the user doesn't have access to the server, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        server_permissions = self.controller.server_perms.get_permissions(mask)
        if EnumPermissionsServer.FILES not in server_permissions:
            # if the user doesn't have Files permission, return an error
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": self.helper.translation.translate(
                        "validators", "insufficientPerms", auth_data[4]["lang"]
                    ),
                },
            )
        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )
        try:
            validate(data, files_operation_schema)
        except ValidationError as why:
            offending_key = ""
            if why.schema.get("fill", None):
                offending_key = why.path[0] if why.path else None
            err = f"""{offending_key} {self.translator.translate(
                "validators",
                why.schema.get("error", "additionalProperties"),
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

        # Check for absolute or relative path. Absolute paths should be deprecated
        server_path = self.controller.servers.get_server_data_by_id(server_id)["path"]
        target_path = Path(
            self.file_helper.get_absolute_path(
                server_path, server_id, data["target_path"]
            )
        )
        source_path = Path(
            self.file_helper.get_absolute_path(
                server_path, server_id, data["source_path"]
            )
        )

        self.helper.validate_traversal(server_path, source_path)
        self.helper.validate_traversal(server_path, target_path)
        try:
            self.move_or_copy(operation, target_path, source_path)
        except shutilError as why:
            return self.finish_json(500, {"status": "error", "error_data": why})
        self.controller.management.add_to_audit_log(
            auth_data[4]["user_id"],
            f"Moved item from {source_path} to {target_path}.",
            server_id,
            self.request.remote_ip,
        )
        return self.finish_json(200, {"status": "ok"})

import logging
import json
import re
import xml.etree.ElementTree as ET
import requests
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from playhouse.shortcuts import model_to_dict
from app.classes.models.server_permissions import EnumPermissionsServer
from app.classes.helpers.cpu_affinity import (
    CpuAffinityValidationError,
    canonicalize_cpu_affinity,
    get_effective_cpu_set,
)
from app.classes.helpers.memory_limit import (
    MemoryLimitValidationError,
    canonicalize_memory_limit_mib,
)
from app.classes.web.base_api_handler import BaseApiHandler

logger = logging.getLogger(__name__)

update_schema = {
    "type": "object",
    "properties": {
        "category": {
            "title": "Jar Category",
            "type": "string",
            "examples": ["Mc_java_servers", "Mc_java_proxies"],
            "error": "enumErr",
            "fill": True,
        },
        "type": {
            "title": "Server JAR Type",
            "type": "string",
            "examples": ["Paper"],
            "minLength": 1,
            "error": "typeString",
            "fill": True,
        },
        "version": {
            "title": "Server JAR Version",
            "type": "string",
            "examples": ["1.18.2"],
            "minLength": 1,
            "error": "typeString",
            "fill": True,
        },
        "mc_version": {
            "title": "Minecraft/Base Version",
            "type": "string",
            "minLength": 1,
            "error": "typeString",
            "fill": True,
        },
        "update_watcher": {
            "title": "Enable Update Notifications",
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
        "cf_project_id": {
            "title": "CurseForge Project ID",
            "type": "integer",
            "minimum": 0,
            "error": "typeIntMinVal0",
            "fill": True,
        },
        "cf_file_id": {
            "title": "CurseForge File ID",
            "type": "integer",
            "minimum": 0,
            "error": "typeIntMinVal0",
            "fill": True,
        },
        "cf_purge_paths": {
            "title": "CurseForge Purge Paths",
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "cf_overlay_dir": {
            "title": "CurseForge Overlay Directory",
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}

# TODO: modify monitoring
server_patch_schema = {
    "type": "object",
    "properties": {
        "server_name": {
            "type": "string",
            "minLength": 2,
            "pattern": r"^[^/\\\\#]*$",
            "error": "serverCreateName",
        },
        "backup_path": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "executable": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "log_path": {
            "type": "string",
            "minLength": 1,
            "error": "serverLogPath",
        },
        "execution_command": {
            "type": "string",
            "minLength": 1,
            "error": "serverExeCommand",
        },
        "cpu_affinity": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "memory_limit_mib": {
            "type": "integer",
            "minimum": 0,
            "error": "typeIntMinVal0",
            "fill": True,
        },
        "telemetry_port": {
            "type": "integer",
            "minimum": 0,
            "maximum": 65535,
            "error": "typeIntMinVal0",
            "fill": True,
        },
        "server_notes": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "java_selection": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "auto_start": {
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
        "auto_start_delay": {
            "type": "integer",
            "minimum": 0,
            "error": "typeIntMinVal0",
            "fill": True,
        },
        "crash_detection": {
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
        "stop_command": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "executable_update_url": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "server_ip": {
            "type": "string",
            "minLength": 1,
            "error": "typeString",
            "fill": True,
        },
        "server_port": {
            "type": "integer",
            "error": "typeInt",
            "fill": True,
        },
        "shutdown_timeout": {
            "type": "integer",
            "minimum": 0,
            "error": "typeIntMinVal0",
            "fill": True,
        },
        "logs_delete_after": {
            "type": "integer",
            "minimum": 0,
            "error": "typeIntMinVal0",
            "fill": True,
        },
        "ignored_exits": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "show_status": {
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
        "count_players": {
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
        "update_watcher": {"type": "boolean", "error": "typeBool", "fill": True},
    },
    "additionalProperties": False,
    "minProperties": 1,
}
basic_server_patch_schema = {
    "type": "object",
    "properties": {
        "server_name": {
            "type": "string",
            "minLength": 1,
            "error": "serverCreateName",
            "fill": True,
        },
        "executable": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "java_selection": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "server_notes": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "auto_start": {
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
        "auto_start_delay": {
            "type": "integer",
            "minimum": 0,
            "error": "typeIntMinVal0",
            "fill": True,
        },
        "crash_detection": {
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
        "stop_command": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "shutdown_timeout": {
            "type": "integer",
            "error": "typeInteger",
            "fill": True,
        },
        "logs_delete_after": {
            "type": "integer",
            "minimum": 0,
            "error": "typeIntMinVal0",
            "fill": True,
        },
        "ignored_exits": {
            "type": "string",
            "error": "typeString",
            "fill": True,
        },
        "count_players": {
            "type": "boolean",
            "error": "typeBool",
            "fill": True,
        },
        "update_watcher": {"type": "boolean", "error": "typeBool", "fill": True},
    },
    "additionalProperties": False,
    "minProperties": 1,
}


class ApiServersServerIndexHandler(BaseApiHandler):
    def get(self, server_id: str):
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

        server_obj = self.controller.servers.get_server_obj(server_id)
        srv_instance = self.controller.servers.get_server_instance_by_id(server_id)
        server = model_to_dict(server_obj)
        status_dict = {
            "update_available": srv_instance.update_available,
            "updating": srv_instance.updating,
            "backing_up": srv_instance.is_backingup,
            "last_backup": srv_instance.last_backup_failed,
        }
        server["status"] = status_dict

        # TODO: limit some columns for specific permissions?
        return self.finish_json(200, {"status": "ok", "data": server})

    def patch(self, server_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError as e:
            return self.finish_json(
                400, {"status": "error", "error": "INVALID_JSON", "error_data": str(e)}
            )
        logger.info(
            "Server update config patch requested for %s with keys: %s",
            server_id,
            list(data.keys()),
        )

        try:
            # prevent general users from becoming bad actors
            if auth_data[4]["superuser"]:
                validate(data, server_patch_schema)
            else:
                validate(data, basic_server_patch_schema)
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

        if "cpu_affinity" in data:
            try:
                data["cpu_affinity"] = canonicalize_cpu_affinity(
                    data["cpu_affinity"],
                    allowed_cpus=get_effective_cpu_set(),
                )
            except CpuAffinityValidationError as why:
                return self.finish_json(
                    400,
                    {
                        "status": "error",
                        "error": "INVALID_CPU_AFFINITY",
                        "error_data": str(why),
                    },
                )
        if "memory_limit_mib" in data:
            try:
                data["memory_limit_mib"] = canonicalize_memory_limit_mib(
                    data["memory_limit_mib"]
                )
            except MemoryLimitValidationError as why:
                return self.finish_json(
                    400,
                    {
                        "status": "error",
                        "error": "INVALID_MEMORY_LIMIT",
                        "error_data": str(why),
                    },
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
        if EnumPermissionsServer.CONFIG not in server_permissions:
            # if the user doesn't have Config permission, return an error
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

        server_obj = self.controller.servers.get_server_obj(server_id)
        java_flag = False
        for key in data:
            # If we don't validate the input there could be security issues
            if key == "java_selection" and data[key] != "none":
                try:
                    command = self.helper.get_execution_java(
                        data[key], server_obj.execution_command
                    )
                    setattr(server_obj, "execution_command", command)
                except ValueError:
                    return self.finish_json(
                        400,
                        {
                            "status": "error",
                            "error": "INVALID EXECUTION COMMAND",
                            "error_data": "INVALID COMMAND",
                        },
                    )
                java_flag = True

            if key != "path":
                if key == "execution_command" and java_flag:
                    continue
                setattr(server_obj, key, data[key])
        self.controller.servers.update_server(server_obj)

        self.controller.management.add_to_audit_log(
            auth_data[4]["user_id"],
            f"modified the server with ID {server_id}",
            server_id,
            self.get_remote_ip(),
        )

        return self.finish_json(200, {"status": "ok"})

    def delete(self, server_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        # DELETE /api/v2/servers/server?files=true
        remove_files = self.get_query_argument("files", None) == "true"

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
        if EnumPermissionsServer.CONFIG not in server_permissions:
            # if the user doesn't have Config permission, return an error
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

        logger.info(
            (
                "Removing server and all associated files for server: "
                if remove_files
                else "Removing server from panel for server: "
            )
            + self.controller.servers.get_server_friendly_name(server_id)
        )

        self.tasks_manager.remove_all_server_tasks(server_id)
        failed = False
        for item in self.controller.servers.failed_servers[:]:
            if item["server_id"] == server_id:
                self.controller.servers.failed_servers.remove(item)
                failed = True

        if failed:
            self.controller.remove_unloaded_server(server_id)
        else:
            self.controller.remove_server(server_id, remove_files)

        self.controller.management.add_to_audit_log(
            auth_data[4]["user_id"],
            f"deleted the server {server_id}",
            server_id,
            self.get_remote_ip(),
        )

        self.finish_json(
            200,
            {"status": "ok"},
        )


class ApiServersServerUpdateConfig(BaseApiHandler):
    FORGE_MAVEN_METADATA_URL = (
        "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"
    )
    NEOFORGE_MAVEN_METADATA_URL = (
        "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
    )

    @staticmethod
    def _fetch_maven_versions(metadata_url: str) -> list[str]:
        response = requests.get(metadata_url, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        versions = [
            version_node.text.strip()
            for version_node in root.findall(".//version")
            if version_node.text and version_node.text.strip()
        ]
        return versions

    @staticmethod
    def _is_safe_version_token(value: str) -> bool:
        return bool(re.fullmatch(r"[0-9A-Za-z._-]+", value))

    @staticmethod
    def _extract_neoforge_branch(default_loader: str) -> str:
        parts = default_loader.split(".")
        if len(parts) < 2:
            return ""
        if not parts[0].isdigit() or not parts[1].isdigit():
            return ""
        return f"{parts[0]}.{parts[1]}."

    def _resolve_catalog_build_versions(
        self, jar_type: str, mc_version: str, default_loader: str
    ) -> list[dict]:
        default_entries = []
        if default_loader:
            default_entries.append(
                {
                    "value": default_loader,
                    "label": default_loader,
                    "source": "bigbucket",
                }
            )

        try:
            if jar_type == "forge-installer":
                if not self._is_safe_version_token(mc_version):
                    return default_entries
                prefix = f"{mc_version}-"
                versions = self._fetch_maven_versions(self.FORGE_MAVEN_METADATA_URL)
                matched = [version for version in versions if version.startswith(prefix)]
                matched.reverse()
                if not matched:
                    return default_entries
                return [
                    {
                        "value": version,
                        "label": f"{version[len(prefix):]} ({version})",
                        "source": "forge-maven",
                    }
                    for version in matched
                ]

            if jar_type == "neoforge-installer":
                versions = self._fetch_maven_versions(self.NEOFORGE_MAVEN_METADATA_URL)
                branch_prefix = self._extract_neoforge_branch(default_loader)
                if branch_prefix:
                    matched = [
                        version for version in versions if version.startswith(branch_prefix)
                    ]
                else:
                    matched = versions[:]
                matched.reverse()
                if not matched:
                    return default_entries
                return [
                    {
                        "value": version,
                        "label": version,
                        "source": "neoforge-maven",
                    }
                    for version in matched
                ]
        except Exception as why:
            logger.warning(
                "Failed to resolve remote build versions for %s (%s): %s",
                jar_type,
                mc_version,
                why,
            )

        return default_entries

    def _build_direct_loader_url(
        self, jar_type: str, selected_version: str, mc_version: str
    ) -> str | None:
        if jar_type == "forge-installer":
            if not selected_version:
                return None
            if not self._is_safe_version_token(selected_version):
                return None
            combined_version = selected_version
            if "-" not in combined_version:
                if not mc_version or not self._is_safe_version_token(mc_version):
                    return None
                combined_version = f"{mc_version}-{selected_version}"
            installer_name = f"forge-{combined_version}-installer.jar"
            return (
                "https://maven.minecraftforge.net/net/minecraftforge/forge/"
                f"{combined_version}/{installer_name}"
            )

        if jar_type == "neoforge-installer":
            if not selected_version or not self._is_safe_version_token(selected_version):
                return None
            installer_name = f"neoforge-{selected_version}-installer.jar"
            return (
                "https://maven.neoforged.net/releases/net/neoforged/neoforge/"
                f"{selected_version}/{installer_name}"
            )

        return None

    def get(self, server_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        if server_id not in [str(x["server_id"]) for x in auth_data[0]]:
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
        if EnumPermissionsServer.CONFIG not in server_permissions:
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

        category = str(self.get_query_argument("category", "")).strip()
        jar_type = str(self.get_query_argument("type", "")).strip()
        mc_version = str(self.get_query_argument("mc_version", "")).strip()
        if not category or not jar_type or not mc_version:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_PARAMS",
                    "error_data": "category, type and mc_version are required.",
                },
            )

        try:
            with open(self.helper.big_bucket_minecraft_cache, "r", encoding="utf-8") as f:
                big_bucket = json.load(f)
            versions = (
                big_bucket.get("categories", {})
                .get(category, {})
                .get("types", {})
                .get(jar_type, {})
                .get("versions", {})
            )
        except Exception as why:
            return self.finish_json(
                500,
                {
                    "status": "error",
                    "error": "CACHE_ERROR",
                    "error_data": str(why),
                },
            )

        version_meta = versions.get(mc_version, {})
        default_loader = str(version_meta.get("loader_version", "") or "").strip()
        build_versions = self._resolve_catalog_build_versions(
            jar_type, mc_version, default_loader
        )
        if not build_versions:
            # Fallback for types that do not expose separate loader builds.
            build_versions = [
                {"value": mc_version, "label": mc_version, "source": "catalog"}
            ]

        return self.finish_json(
            200,
            {
                "status": "ok",
                "data": {
                    "build_versions": build_versions,
                    "default_loader": default_loader,
                },
            },
        )

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
        if EnumPermissionsServer.CONFIG not in server_permissions:
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
            validate(data, update_schema)
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
        server_obj = self.controller.servers.get_server_obj(server_id)
        if "version" in data:
            big_bucket = {}
            with open(
                self.helper.big_bucket_minecraft_cache, "r", encoding="utf-8"
            ) as f:
                big_bucket = json.load(f)
            selected_version = str(data.get("version", "") or "").strip()
            category = str(data.get("category", "") or "").strip()
            jar_type = str(data.get("type", "") or "").strip()
            mc_version = str(data.get("mc_version", "") or "").strip()

            # Backward compatibility with old "category|type|version" payloads.
            if selected_version.count("|") == 2 and not category and not jar_type:
                category, jar_type, selected_version = selected_version.split("|", 2)
            # Backward compatibility with "type" still sent as "category|type".
            if "|" in jar_type:
                maybe_category, maybe_type = jar_type.split("|", 1)
                if not category:
                    category = maybe_category
                jar_type = maybe_type

            if not category or not jar_type or not selected_version:
                return self.finish_json(
                    400,
                    {
                        "status": "error",
                        "error": "INVALID_UPDATE_SELECTION",
                        "error_data": "category, type and version are required.",
                    },
                )

            url = None
            try:
                url = (
                    big_bucket["categories"][category]["types"][jar_type]["versions"][
                        selected_version
                    ]["url"][0]
                )
            except KeyError:
                url = self._build_direct_loader_url(
                    jar_type=jar_type,
                    selected_version=selected_version,
                    mc_version=mc_version,
                )
                if not url:
                    return self.finish_json(
                        400,
                        {
                            "status": "error",
                            "error": "INVALID_UPDATE_SELECTION",
                            "error_data": (
                                "Selected version is not available in catalog and "
                                "could not be resolved as a Forge/NeoForge build."
                            ),
                        },
                    )
            server_obj.executable_update_url = url
        for key in ("cf_project_id", "cf_file_id", "cf_purge_paths", "cf_overlay_dir"):
            if key in data:
                setattr(server_obj, key, data[key])
        if "update_watcher" in data:
            server_obj.update_watcher = data.get("update_watcher")

        self.controller.servers.update_server(server_obj)
        self.controller.servers.refresh_server_settings(server_id)
        server_instance = self.controller.servers.get_server_instance_by_id(server_id)

        self.controller.management.add_to_audit_log(
            auth_data[4]["user_id"],
            f"modified the server with ID {server_id}",
            server_id,
            self.get_remote_ip(),
        )
        server_instance.check_server_version()  # check for a new version after instance
        # is updated
        return self.finish_json(
            200,
            {
                "status": "ok",
                "data": {
                    "executable_update_url": server_obj.executable_update_url,
                    "cf_project_id": server_obj.cf_project_id,
                    "cf_file_id": server_obj.cf_file_id,
                    "cf_purge_paths": server_obj.cf_purge_paths,
                    "cf_overlay_dir": server_obj.cf_overlay_dir,
                },
            },
        )

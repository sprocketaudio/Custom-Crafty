import logging
import html
from pathlib import Path
from app.classes.models.server_permissions import EnumPermissionsServer
from app.classes.web.base_api_handler import BaseApiHandler

logger = logging.getLogger(__name__)
ID_MISMATCH = "Server ID backup server ID different"
GENERAL_AUTH_ERROR = "Authorization Error"


class ApiServersServerBackupsBackupDownloadHandler(BaseApiHandler):
    async def get(self, server_id: str, backup_id: str, encoded_file_name: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return
        backup_conf = self.controller.management.get_backup_config(backup_id)
        raw_file_name = html.unescape(encoded_file_name)
        file_name = Path(
            backup_conf["backup_location"], str(backup_conf["backup_id"]), raw_file_name
        )
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
        if not self.helper.validate_traversal(
            backup_conf["backup_location"], file_name
        ):
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "NOT_AUTHORIZED",
                    "error_data": GENERAL_AUTH_ERROR,
                },
            )
        if not self.helper.check_file_exists(str(file_name)):
            return self.finish_json(
                404,
                {
                    "status": "error",
                    "error": "NOT_FOUND",
                    "error_data": "File does not exist",
                },
            )
        await self.download_file(file_name)

        # Do not remove file after download. user may still want it

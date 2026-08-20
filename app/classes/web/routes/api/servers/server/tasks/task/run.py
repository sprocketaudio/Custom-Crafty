from app.classes.models.server_permissions import EnumPermissionsServer
from app.classes.web.base_api_handler import BaseApiHandler


class ApiServersServerTasksTaskRunHandler(BaseApiHandler):
    """Queue an existing schedule for immediate execution."""

    def post(self, server_id: str, task_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return
        if server_id not in [str(item["server_id"]) for item in auth_data[0]]:
            return self._not_authorized(auth_data)

        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        if (
            EnumPermissionsServer.SCHEDULE
            not in self.controller.server_perms.get_permissions(mask)
        ):
            return self._not_authorized(auth_data)

        try:
            self.tasks_manager.run_task_now(task_id, auth_data[4]["user_id"], server_id)
        except Exception as why:
            return self.finish_json(
                400,
                {"status": "error", "error": "RUN_TASK_FAILED", "error_data": str(why)},
            )

        self.controller.management.add_to_audit_log(
            auth_data[4]["user_id"],
            f"Ran scheduled task {task_id} manually for server {server_id}",
            server_id,
            self.get_remote_ip(),
        )
        return self.finish_json(200, {"status": "ok"})

    def _not_authorized(self, auth_data):
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

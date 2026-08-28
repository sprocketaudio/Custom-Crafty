"""Copy all schedules from one authorized server to another."""

import json

from app.classes.models.management import Schedules
from app.classes.models.server_permissions import EnumPermissionsServer
from app.classes.web.base_api_handler import BaseApiHandler


class ApiServersServerTasksCopyHandler(BaseApiHandler):
    """Replace a server's schedules with a copy from another server."""

    def _has_schedule_permission(self, auth_data, server_id: str) -> bool:
        if server_id not in [str(server["server_id"]) for server in auth_data[0]]:
            return False
        mask = self.controller.server_perms.get_lowest_api_perm_mask(
            self.controller.server_perms.get_user_permissions_mask(
                auth_data[4]["user_id"], server_id
            ),
            auth_data[5],
        )
        return (
            EnumPermissionsServer.SCHEDULE
            in self.controller.server_perms.get_permissions(mask)
        )

    def post(self, server_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        try:
            data = json.loads(self.request.body)
            source_server_id = str(data["source_server_id"])
        except (json.JSONDecodeError, KeyError, TypeError) as ex:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_COPY_SOURCE",
                    "error_data": "source_server_id is required.",
                },
            )

        if source_server_id == server_id:
            return self.finish_json(
                400,
                {
                    "status": "error",
                    "error": "INVALID_COPY_SOURCE",
                    "error_data": "Choose a different source server.",
                },
            )

        if not (
            self._has_schedule_permission(auth_data, server_id)
            and self._has_schedule_permission(auth_data, source_server_id)
        ):
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

        source_schedules = list(
            self.controller.management.get_schedules_by_server(source_server_id)
        )
        if any(schedule.action == "backup_server" for schedule in source_schedules):
            return self.finish_json(
                409,
                {
                    "status": "error",
                    "error": "SERVER_SPECIFIC_BACKUP_SCHEDULE",
                    "error_data": (
                        "Backup schedules cannot be copied because their backup "
                        "configuration belongs to the source server."
                    ),
                },
            )

        # Remove existing persisted schedules and their APScheduler jobs only after all
        # validation has completed. Reaction parents are remapped below after every new
        # schedule has an ID on the target server.
        self.tasks_manager.remove_all_server_tasks(server_id)

        schedule_id_map = {}
        copied_schedules = []
        with Schedules._meta.database.atomic():
            for source_schedule in source_schedules:
                copied_id = self.controller.management.create_scheduled_task(
                    server_id,
                    source_schedule.action,
                    source_schedule.interval,
                    source_schedule.interval_type,
                    source_schedule.start_time,
                    source_schedule.command,
                    source_schedule.name,
                    source_schedule.enabled,
                    source_schedule.one_time,
                    source_schedule.cron_string,
                    None,
                    source_schedule.delay,
                    None,
                )
                schedule_id_map[source_schedule.schedule_id] = copied_id
                copied_schedules.append(copied_id)

            for source_schedule in source_schedules:
                if source_schedule.parent not in schedule_id_map:
                    continue
                self.controller.management.update_scheduled_task(
                    schedule_id_map[source_schedule.schedule_id],
                    {"parent": schedule_id_map[source_schedule.parent]},
                )

        # Add only enabled non-reaction schedules to APScheduler. Reaction schedules
        # are invoked by their remapped parent and never have their own scheduler job.
        system_user_id = self.tasks_manager.users_controller.get_id_by_name("system")
        for copied_id in copied_schedules:
            copied_schedule = self.controller.management.get_scheduled_task_model(copied_id)
            if not copied_schedule.enabled or copied_schedule.interval_type == "reaction":
                continue
            new_job = self.tasks_manager._add_db_schedule(copied_schedule, system_user_id)
            if new_job is not None:
                self.controller.management.update_scheduled_task(
                    copied_id,
                    {"next_run": new_job.next_run_time.strftime("%m/%d/%Y, %H:%M:%S")},
                )

        self.controller.management.add_to_audit_log(
            auth_data[4]["user_id"],
            f"Edited server {server_id}: copied {len(copied_schedules)} schedules "
            f"from server {source_server_id}",
            server_id,
            self.get_remote_ip(),
        )
        self.tasks_manager.reload_schedule_from_db()
        return self.finish_json(
            200,
            {"status": "ok", "data": {"copied": len(copied_schedules)}},
        )

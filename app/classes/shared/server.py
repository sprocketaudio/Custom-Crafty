from contextlib import redirect_stderr, suppress
import os
import io
import re
import shutil
import time
import sys
import datetime
import threading
import logging
import subprocess
import html
import glob
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError
import requests

# TZLocal is set as a hidden import on win pipeline
from tzlocal import get_localzone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError, ConflictingIdError

# OpenMetrics/Prometheus Imports
from prometheus_client import CollectorRegistry, Gauge, Info

from app.classes.remote_stats.stats import Stats
from app.classes.remote_stats.nitrado_ping import NitradoPing
from app.classes.remote_stats.ping import ping, ping_raknet
from app.classes.models.servers import HelperServers, Servers
from app.classes.models.server_stats import HelperServerStats
from app.classes.models.management import HelpersManagement, HelpersWebhooks
from app.classes.models.users import HelperUsers
from app.classes.models.server_permissions import PermissionsServers
from app.classes.shared.console import Console
from app.classes.helpers.helpers import Helpers
from app.classes.helpers.cpu_affinity import (
    CpuAffinityValidationError,
    canonicalize_cpu_affinity,
    get_effective_cpu_set,
)
from app.classes.helpers.memory_limit import (
    MemoryLimitValidationError,
    canonicalize_memory_limit_mib,
)
from app.classes.helpers.telemetry import (
    build_telemetry_url,
    normalize_telemetry_port,
    parse_telemetry_payload,
)
from app.classes.helpers.file_helpers import FileHelpers
from app.classes.shared.null_writer import NullWriter
from app.classes.shared.websocket_manager import WebSocketManager
from app.classes.steamcmd.steamcmd import SteamCMD
from app.classes.web.webhooks.webhook_factory import WebhookFactory

with redirect_stderr(NullWriter()):
    import psutil
    from psutil import NoSuchProcess

logger = logging.getLogger(__name__)
SUCCESSMSG = "SUCCESS! Forge install completed"


def extract_backup_info(res) -> dict:
    if not isinstance(res, dict):
        return {}
    return {
        "backup_name": res.get("backup_name"),
        "backup_size": str(res.get("backup_size")),
        "backup_link": res.get("backup_link"),
        "backup_status": res.get("backup_status"),
        "backup_error": res.get("backup_error"),
    }


def build_event_data(server, command, event_type, backup_info):
    event_data = {
        "server_name": server.name,
        "server_id": server.server_id,
        "command": command,
        "event_type": event_type,
        **backup_info,
    }
    return event_data


def process_webhook(swebhook, server, command, event_type, res):
    webhook = HelpersWebhooks.get_webhook_by_id(swebhook.id)
    webhook_provider = WebhookFactory.create_provider(webhook["webhook_type"])

    backup_info = extract_backup_info(res)
    event_data = build_event_data(server, command, event_type, backup_info)
    event_data = webhook_provider.add_time_variables(event_data)

    if res is not False and swebhook.enabled:
        webhook_provider.send(
            server_name=server.name,
            title=webhook["name"],
            url=webhook["url"],
            message_template=webhook["body"],
            event_data=event_data,
            color=webhook["color"],
            bot_name=webhook["bot_name"],
        )


def send_webhook(event_type: str, res, command: str, args):
    server = args[0]
    server_webhooks = HelpersWebhooks.get_webhooks_by_server(server.server_id, True)
    for swebhook in server_webhooks:
        if event_type in str(swebhook.trigger).split(","):
            logger.info(
                f"Found callback for event {event_type} for server {server.server_id}"
            )
            process_webhook(swebhook, server, command, event_type, res)


def callback(called_func):
    # Usage of @callback on method
    # definition to run a webhook check
    # on method completion
    def wrapper(*args, **kwargs):
        res = None
        logger.debug("Checking for callbacks")
        try:
            res = called_func(*args, **kwargs)  # Calls and runs the function
        finally:
            event_type = called_func.__name__

            # For send_command, Retrieve command from args or kwargs
            command = args[1] if len(args) > 1 else kwargs.get("command", "")

            if event_type in WebhookFactory.get_monitored_events():
                send_webhook(event_type, res, command, args)
        return res

    return wrapper


class ServerOutBuf:
    lines = {}

    def __init__(self, helper, proc, server_id):
        self.helper = helper
        self.proc = proc
        self.server_id = str(server_id)
        # Buffers text for virtual_terminal_lines config number of lines
        self.max_lines = self.helper.get_setting("virtual_terminal_lines")
        self.line_buffer = ""
        ServerOutBuf.lines[self.server_id] = []

    def process_byte(self, char):
        if char == "\n":
            line = self.line_buffer.rstrip("\r")
            ServerOutBuf.lines[self.server_id].append(line)

            self.new_line_handler(line)
            self.line_buffer = ""
            # Limit list length to self.max_lines:
            if len(ServerOutBuf.lines[self.server_id]) > self.max_lines:
                ServerOutBuf.lines[self.server_id].pop(0)
        else:
            self.line_buffer += char

    def check(self):
        text_wrapper = io.TextIOWrapper(
            self.proc.stdout, encoding="UTF-8", errors="ignore", newline=""
        )
        while True:
            if self.proc.poll() is None:
                char = text_wrapper.read(1)  # modified
                # TODO: we may want to benchmark reading in blocks and userspace
                # processing it later, reads are kind of expensive as a syscall
                self.process_byte(char)
            else:
                flush = text_wrapper.read()  # modified
                for char in flush:
                    self.process_byte(char)
                break

    def new_line_handler(self, new_line):
        new_line = re.sub("(\033\\[(0;)?[0-9]*[A-z]?(;[0-9])?m?)", " ", new_line)
        new_line = re.sub("[A-z]{2}\b\b", "", new_line)
        highlighted = self.helper.log_colors(html.escape(new_line))

        logger.debug("Broadcasting new virtual terminal line")

        # TODO: Do not send data to clients who do not have permission to view
        # this server's console
        if len(WebSocketManager().clients) > 0:
            WebSocketManager().broadcast_page_params(
                "/panel/server_detail",
                {"id": self.server_id},
                "vterm_new_line",
                {"line": highlighted + "<br />"},
            )


# **********************************************************************************
#                               Minecraft Server Class
# **********************************************************************************
class ServerInstance:
    server_object: Servers
    helper: Helpers
    file_helper: FileHelpers
    management_helper: HelpersManagement
    stats: Stats
    stats_helper: HelperServerStats

    def __init__(
        self,
        server_id,
        helper,
        management_helper,
        stats,
        file_helper,
        backup_mgr,
        import_helper,
    ):
        self.helper = helper
        self.file_helper = file_helper
        self.management_helper = management_helper
        self.backup_mgr = backup_mgr
        self.import_helper = import_helper
        # holders for our process
        self.process = None
        self.line = False
        self.start_time = None
        self.server_command = None
        self.server_path = None
        self.server_thread = None
        self.settings = {}
        self.updating = False
        self.server_id = server_id
        self.jar_update_url = None
        self.name = None
        self.is_crashed = False
        self.restart_count = 0
        self._game_port_cache = None
        self.stats = stats
        self.server_object = HelperServers.get_server_obj(self.server_id)
        self.stats_helper = HelperServerStats(self.server_id)
        self.last_backup_failed = False
        self.server_registry = CollectorRegistry()

        try:
            with open(
                os.path.join(
                    self.helper.root_dir,
                    "app",
                    "config",
                    "db",
                    "servers",
                    self.server_id,
                    "players_cache.json",
                ),
                "r",
                encoding="utf-8",
            ) as f:
                self.player_cache = list(json.load(f).values())
        except:
            self.player_cache = []
        try:
            self.tz = get_localzone()
        except ZoneInfoNotFoundError as e:
            logger.error(
                "Could not capture time zone from system. Falling back to Europe/London"
                f" error: {e}"
            )
            self.tz = ZoneInfo("Europe/London")
        self.server_scheduler = BackgroundScheduler(timezone=str(self.tz))
        self.dir_scheduler = BackgroundScheduler(timezone=str(self.tz))
        self.init_registries()
        self.server_scheduler.start()
        self.dir_scheduler.start()
        self.start_dir_calc_task()
        self.is_backingup = False
        # Reset crash and update at initialization
        self.stats_helper.server_crash_reset()
        self.stats_helper.set_update(False)
        # Start update watcher
        self.server_scheduler.add_job(
            self.check_server_version,
            "interval",
            hours=12,
            id=f"{str(self.server_id)}_update_watcher",
        )
        self.update_available = False
        self._active_launch_command = []
        self._active_cpu_affinity = ""
        self._active_memory_limit_mib = 0
        self._active_memory_limit_bytes = 0
        self._active_memory_cgroup_path = ""

    # **********************************************************************************
    #                               Minecraft Server Management
    # **********************************************************************************
    def update_server_instance(self):
        server_data: Servers = HelperServers.get_server_obj(self.server_id)
        self.server_path = server_data.path
        self.jar_update_url = server_data.executable_update_url
        self.name = server_data.server_name
        self.server_object = server_data
        self.stats_helper.select_database()
        self.reload_server_settings()

    def reload_server_settings(self):
        server_data = HelperServers.get_server_data_by_id(self.server_id)
        self.settings = server_data

    def do_server_setup(self, server_data_obj):
        server_id = server_data_obj["server_id"]
        server_name = server_data_obj["server_name"]
        auto_start = server_data_obj["auto_start"]

        logger.info(
            f"Creating Server object: {server_id} | "
            f"Server Name: {server_name} | "
            f"Auto Start: {auto_start}"
        )
        self.server_id = server_id
        self.name = server_name
        self.settings = server_data_obj
        # Check update relies on up to date information from self.settings.
        self.check_server_version()
        # Running it after instead of during init function

        self.record_server_stats()

        # build our server run command

        if server_data_obj["auto_start"]:
            delay = int(self.settings["auto_start_delay"])

            logger.info(f"Scheduling server {self.name} to start in {delay} seconds")
            Console.info(f"Scheduling server {self.name} to start in {delay} seconds")

            self.server_scheduler.add_job(
                self.run_scheduled_server,
                "interval",
                seconds=delay,
                id=str(self.server_id),
            )

    def run_scheduled_server(self):
        Console.info(f"Starting server ID: {self.server_id} - {self.name}")
        logger.info(f"Starting server ID: {self.server_id} - {self.name}")
        # Sets waiting start to false since we're attempting to start the server.
        self.stats_helper.set_waiting_start(False)
        self.run_threaded_server(None)

        # remove the scheduled job since it's ran
        return self.server_scheduler.remove_job(str(self.server_id))

    def run_threaded_server(self, user_id, forge_install=False):
        # start the server
        self.server_thread = threading.Thread(
            target=self.start_server,
            daemon=True,
            args=(
                user_id,
                forge_install,
            ),
            name=f"{self.server_id}_server_thread",
        )
        self.server_thread.start()

        # Register an shedule for polling server stats when running
        logger.info(f"Polling server statistics {self.name} every {5} seconds")
        Console.info(f"Polling server statistics {self.name} every {5} seconds")
        try:
            self.server_scheduler.add_job(
                self.realtime_stats,
                "interval",
                seconds=5,
                id="stats_" + str(self.server_id),
            )
        except:
            self.server_scheduler.remove_job("stats_" + str(self.server_id))
            self.server_scheduler.add_job(
                self.realtime_stats,
                "interval",
                seconds=5,
                id="stats_" + str(self.server_id),
            )
        logger.info(f"Saving server statistics {self.name} every {30} seconds")
        Console.info(f"Saving server statistics {self.name} every {30} seconds")
        try:
            self.server_scheduler.add_job(
                self.record_server_stats,
                "interval",
                seconds=30,
                id="save_stats_" + str(self.server_id),
            )
        except ConflictingIdError:
            self.server_scheduler.remove_job("save_stats_" + str(self.server_id))
            self.server_scheduler.add_job(
                self.record_server_stats,
                "interval",
                seconds=30,
                id="save_stats_" + str(self.server_id),
            )

    def setup_server_run_command(self):
        # configure the server
        server_exec_path = Helpers.get_os_understandable_path(
            self.settings["executable"]
        )
        self.server_command = Helpers.cmdparse(self.settings["execution_command"])
        if self.helper.is_os_windows() and self.server_command[0] == "java":
            logger.info(
                "Detected nebulous java in start command. "
                "Replacing with full java path."
            )
            oracle_path = shutil.which("java")
            if oracle_path:
                # Checks for Oracle Java. Only Oracle Java's helper will cause a re-exec
                if "/Oracle/Java/" in str(self.helper.wtol_path(oracle_path)):
                    logger.info(
                        "Oracle Java detected. Changing start command to avoid re-exec."
                    )
                    which_java_raw = self.helper.which_java()
                    try:
                        java_path = which_java_raw + "\\bin\\java"
                    except TypeError:
                        logger.warning(
                            "Could not find java in the registry even though"
                            " Oracle java is installed."
                            " Re-exec expected, but we have no"
                            " other options. CPU stats will not work for process."
                        )
                        java_path = ""
                    if str(which_java_raw) != str(
                        self.helper.get_servers_root_dir
                    ) or str(self.helper.get_servers_root_dir) in str(which_java_raw):
                        if java_path != "":
                            self.server_command[0] = java_path
                    else:
                        logger.critcal(
                            "Possible attack detected. User attempted to exec "
                            "java binary from server directory."
                        )
                        return
        self.server_path = Helpers.get_os_understandable_path(self.settings["path"])

        # let's do some quick checking to make sure things actually exists
        full_path = os.path.join(self.server_path, server_exec_path)
        if not Helpers.check_file_exists(full_path):
            logger.critical(
                f"Server executable path: {full_path} does not seem to exist"
            )
            Console.critical(
                f"Server executable path: {full_path} does not seem to exist"
            )

        if not Helpers.check_path_exists(self.server_path):
            logger.critical(f"Server path: {self.server_path} does not seem to exits")
            Console.critical(f"Server path: {self.server_path} does not seem to exits")

        if not Helpers.check_writeable(self.server_path):
            logger.critical(f"Unable to write/access {self.server_path}")
            Console.critical(f"Unable to write/access {self.server_path}")

    def _launch_server_process(self, command=None, env=None):
        popen_kwargs = {
            "cwd": self.server_path,
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
        }
        if env is not None:
            popen_kwargs["env"] = env
        launch_command = command if command is not None else self.server_command
        self._active_launch_command = list(launch_command or [])
        return subprocess.Popen(launch_command, **popen_kwargs)

    def _get_configured_cpu_affinity(self):
        return str(self.settings.get("cpu_affinity", "") or "").strip()

    def _get_cpu_affinity_capability(self):
        caps = getattr(self.helper, "launch_capabilities", None)
        cpu_caps = {}
        if isinstance(caps, dict):
            cpu_caps = caps.get("cpu_affinity", {}) or {}
        if not cpu_caps:
            detected_caps = self.helper.detect_launch_capabilities()
            cpu_caps = detected_caps.get("cpu_affinity", {}) or {}
        return cpu_caps

    @staticmethod
    def _sanitize_server_id_for_cgroup(server_id):
        return re.sub(r"[^A-Za-z0-9_.-]", "_", str(server_id))

    def _get_configured_memory_limit_mib(self):
        return canonicalize_memory_limit_mib(self.settings.get("memory_limit_mib", 0))

    def _get_memory_limit_capability(self):
        caps = getattr(self.helper, "launch_capabilities", None)
        memory_caps = {}
        if isinstance(caps, dict):
            memory_caps = caps.get("memory_limit", {}) or {}
        if not memory_caps:
            detected_caps = self.helper.detect_launch_capabilities()
            memory_caps = detected_caps.get("memory_limit", {}) or {}
        return memory_caps

    def _build_server_memory_cgroup_path(self, memory_caps):
        cgroup_root = memory_caps.get("cgroup_root", "")
        if cgroup_root:
            root_path = Path(cgroup_root).resolve(strict=False)
        else:
            root_path = Path("/sys/fs/cgroup/crafty")
        server_component = self._sanitize_server_id_for_cgroup(self.server_id)
        return root_path / f"server-{server_component}"

    def _configure_memory_limit_cgroup(self, memory_limit_mib, memory_caps):
        cgroup_path = self._build_server_memory_cgroup_path(memory_caps)
        memory_limit_bytes = int(memory_limit_mib) * 1024 * 1024
        cgroup_path.mkdir(parents=True, exist_ok=True)
        (cgroup_path / "memory.max").write_text(str(memory_limit_bytes), encoding="utf-8")
        with suppress(OSError):
            memory_oom_group = cgroup_path / "memory.oom.group"
            if memory_oom_group.exists():
                memory_oom_group.write_text("1", encoding="utf-8")
        return str(cgroup_path), memory_limit_bytes

    def _prepare_memory_limit_policy(self, user_id, user_lang):
        self._active_memory_limit_mib = 0
        self._active_memory_limit_bytes = 0
        self._active_memory_cgroup_path = ""

        try:
            requested_limit_mib = self._get_configured_memory_limit_mib()
        except MemoryLimitValidationError as ex:
            self._log_launch_event(
                "launch_blocked",
                level=logging.ERROR,
                reason="invalid_memory_limit",
                configured_memory_limit=self.settings.get("memory_limit_mib", 0),
                error=str(ex),
            )
            self._notify_start_error(user_id, user_lang, f"Memory limit is invalid: {str(ex)}")
            return False

        if requested_limit_mib <= 0:
            return True

        memory_caps = self._get_memory_limit_capability()
        if not memory_caps.get("supported", False):
            self._log_launch_event(
                "launch_blocked",
                level=logging.ERROR,
                reason="memory_limit_unsupported",
                configured_memory_limit_mib=requested_limit_mib,
                capability_reason=memory_caps.get("reason", "unknown"),
                capability_os=memory_caps.get("os", ""),
                cgroup_root=memory_caps.get("cgroup_root", ""),
            )
            self._notify_start_error(
                user_id,
                user_lang,
                "Memory limit requires Linux cgroup v2 memory controller support.",
            )
            return False

        try:
            cgroup_path, memory_limit_bytes = self._configure_memory_limit_cgroup(
                requested_limit_mib,
                memory_caps,
            )
        except OSError as ex:
            self._log_launch_event(
                "launch_blocked",
                level=logging.ERROR,
                reason="memory_cgroup_config_failed",
                configured_memory_limit_mib=requested_limit_mib,
                cgroup_root=memory_caps.get("cgroup_root", ""),
                error=str(ex),
            )
            self._notify_start_error(
                user_id,
                user_lang,
                f"Failed to configure memory cgroup limit: {str(ex)}",
            )
            return False

        self._active_memory_limit_mib = requested_limit_mib
        self._active_memory_limit_bytes = memory_limit_bytes
        self._active_memory_cgroup_path = cgroup_path
        self._log_launch_event(
            "memory_limit_applied",
            configured_memory_limit_mib=requested_limit_mib,
            configured_memory_limit_bytes=memory_limit_bytes,
            cgroup_path=cgroup_path,
        )
        return True

    def _attach_process_to_memory_cgroup(self, user_id, user_lang, forge_install=False):
        if self.process is None or not self._active_memory_cgroup_path:
            return True

        cgroup_procs_path = Path(self._active_memory_cgroup_path) / "cgroup.procs"
        try:
            cgroup_procs_path.write_text(str(self.process.pid), encoding="utf-8")
        except OSError as ex:
            self._log_launch_event(
                "launch_failure",
                level=logging.ERROR,
                reason="memory_cgroup_attach_failed",
                pid=self.process.pid,
                cgroup_path=self._active_memory_cgroup_path,
                error=str(ex),
            )
            with suppress(Exception):
                self.process.kill()
            self.cleanup_server_object()
            self._notify_start_error(
                user_id,
                user_lang,
                f"Failed to attach process to memory cgroup: {str(ex)}",
            )
            if forge_install:
                self.stats_helper.finish_import()
            return False
        return True

    @staticmethod
    def _read_effective_memory_cgroup(pid):
        if not isinstance(pid, int):
            return None
        if not sys.platform.startswith("linux"):
            return None

        cgroup_path = Path("/proc", str(pid), "cgroup")
        try:
            with open(cgroup_path, "r", encoding="utf-8") as cgroup_file:
                for line in cgroup_file:
                    if line.startswith("0::"):
                        return line.strip().split("::", 1)[1]
        except OSError:
            return None
        return None

    def _log_effective_memory_limit_state(self):
        if self.process is None or self._active_memory_limit_mib <= 0:
            return

        effective_cgroup = self._read_effective_memory_cgroup(self.process.pid)
        if effective_cgroup is None:
            self._log_launch_event(
                "memory_limit_verify_unavailable",
                level=logging.WARNING,
                pid=self.process.pid,
                configured_memory_limit_mib=self._active_memory_limit_mib,
                cgroup_path=self._active_memory_cgroup_path,
            )
            return

        self._log_launch_event(
            "memory_limit_verify",
            pid=self.process.pid,
            configured_memory_limit_mib=self._active_memory_limit_mib,
            configured_memory_limit_bytes=self._active_memory_limit_bytes,
            cgroup_path=self._active_memory_cgroup_path,
            effective_cgroup=effective_cgroup,
        )

    def _resolve_launch_command(self, user_id, user_lang):
        base_command = list(self.server_command or [])
        self._active_launch_command = list(base_command)
        self._active_cpu_affinity = ""

        requested_affinity = self._get_configured_cpu_affinity()
        if requested_affinity == "":
            return base_command

        try:
            canonical_affinity = canonicalize_cpu_affinity(
                requested_affinity,
                allowed_cpus=get_effective_cpu_set(),
            )
        except CpuAffinityValidationError as ex:
            self._log_launch_event(
                "launch_blocked",
                level=logging.ERROR,
                reason="invalid_cpu_affinity",
                requested_cpu_affinity=requested_affinity,
                error=str(ex),
            )
            self._notify_start_error(
                user_id, user_lang, f"CPU affinity is invalid: {str(ex)}"
            )
            return None

        cpu_caps = self._get_cpu_affinity_capability()
        if not cpu_caps.get("supported", False):
            self._log_launch_event(
                "launch_blocked",
                level=logging.ERROR,
                reason="cpu_affinity_unsupported",
                requested_cpu_affinity=requested_affinity,
                canonical_cpu_affinity=canonical_affinity,
                capability_reason=cpu_caps.get("reason", "unknown"),
                capability_os=cpu_caps.get("os", ""),
            )
            self._notify_start_error(
                user_id, user_lang, "CPU affinity requires Linux + taskset."
            )
            return None

        taskset_path = cpu_caps.get("taskset_path") or shutil.which("taskset")
        if not taskset_path:
            self._log_launch_event(
                "launch_blocked",
                level=logging.ERROR,
                reason="cpu_affinity_taskset_missing",
                requested_cpu_affinity=requested_affinity,
                canonical_cpu_affinity=canonical_affinity,
            )
            self._notify_start_error(
                user_id, user_lang, "CPU affinity requires taskset but it is unavailable."
            )
            return None

        launch_command = [taskset_path, "--cpu-list", canonical_affinity, *base_command]
        self._active_launch_command = launch_command
        self._active_cpu_affinity = canonical_affinity
        self._log_launch_event(
            "cpu_affinity_applied",
            requested_cpu_affinity=requested_affinity,
            canonical_cpu_affinity=canonical_affinity,
            taskset_path=taskset_path,
        )
        return launch_command

    def _build_launch_event_payload(self, **extra):
        payload = {
            "server_id": self.server_id,
            "server_name": self.name,
            "server_type": self.settings.get("type"),
            "cwd": self.server_path,
            "argv": [str(arg) for arg in (self._active_launch_command or [])],
        }
        if self._active_cpu_affinity:
            payload["active_cpu_affinity"] = self._active_cpu_affinity
        if self._active_memory_limit_mib > 0:
            payload["active_memory_limit_mib"] = self._active_memory_limit_mib
            payload["active_memory_limit_bytes"] = self._active_memory_limit_bytes
        if self._active_memory_cgroup_path:
            payload["active_memory_cgroup_path"] = self._active_memory_cgroup_path
        payload.update(extra)
        return payload

    @staticmethod
    def _read_effective_cpu_affinity(pid):
        if not isinstance(pid, int):
            return None
        if not sys.platform.startswith("linux"):
            return None

        status_path = Path("/proc", str(pid), "status")
        try:
            with open(status_path, "r", encoding="utf-8") as status_file:
                for line in status_file:
                    if line.startswith("Cpus_allowed_list:"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            return None
        return None

    def _log_effective_cpu_affinity_state(self):
        if not self._active_cpu_affinity or self.process is None:
            return

        effective_affinity = self._read_effective_cpu_affinity(self.process.pid)
        if effective_affinity is None:
            self._log_launch_event(
                "cpu_affinity_verify_unavailable",
                level=logging.WARNING,
                pid=self.process.pid,
                canonical_cpu_affinity=self._active_cpu_affinity,
            )
            return

        self._log_launch_event(
            "cpu_affinity_verify",
            pid=self.process.pid,
            canonical_cpu_affinity=self._active_cpu_affinity,
            effective_cpu_affinity=effective_affinity,
        )

    def _log_launch_event(self, event_name, level=logging.INFO, **extra):
        payload = self._build_launch_event_payload(event=event_name, **extra)
        logger.log(
            level,
            "launch_event %s",
            json.dumps(payload, ensure_ascii=True, sort_keys=True),
        )

    def _notify_start_error(self, user_id, user_lang, detail, channel="send_error"):
        if not user_id:
            return
        error_message = self.helper.translation.translate(
            "error", "start-error", user_lang
        ).format(self.name, detail)
        WebSocketManager().broadcast_user(
            user_id,
            channel,
            {"error": error_message},
        )

    @staticmethod
    def _get_wrapper_policy_mode():
        mode = os.environ.get("CRAFTY_WRAPPER_POLICY_MODE", "disabled").strip().lower()
        if mode not in {"disabled", "audit", "enforce"}:
            logger.warning(
                "Unknown CRAFTY_WRAPPER_POLICY_MODE value %r. "
                "Defaulting to 'disabled'.",
                mode,
            )
            return "disabled"
        return mode

    @staticmethod
    def _get_wrapper_startup_grace_seconds():
        default_seconds = 5
        raw = os.environ.get("CRAFTY_WRAPPER_GRACE_SECONDS")
        if raw is None:
            return default_seconds
        try:
            grace = int(raw)
        except ValueError:
            logger.warning(
                "Invalid CRAFTY_WRAPPER_GRACE_SECONDS value %r. "
                "Using default %s.",
                raw,
                default_seconds,
            )
            return default_seconds
        return max(1, min(30, grace))

    @staticmethod
    def _snapshot_process_children(pid):
        try:
            process = psutil.Process(pid)
            children = process.children(recursive=True)
        except (NoSuchProcess, Exception):
            return []

        child_data = []
        for child in children:
            try:
                cmdline = " ".join(child.cmdline())
            except Exception:
                cmdline = ""
            try:
                name = child.name()
            except Exception:
                name = ""
            try:
                ppid = child.ppid()
            except Exception:
                ppid = None
            child_data.append(
                {
                    "pid": child.pid,
                    "ppid": ppid,
                    "name": name,
                    "cmdline": cmdline,
                }
            )
        return child_data

    @staticmethod
    def _filter_alive_pids(process_data):
        alive = []
        for proc in process_data:
            pid = proc.get("pid")
            if isinstance(pid, int) and psutil.pid_exists(pid):
                alive.append(proc)
        return alive

    def _inspect_wrapper_process_shape(self, parent_pid):
        grace_seconds = self._get_wrapper_startup_grace_seconds()
        deadline = time.monotonic() + grace_seconds
        last_seen_children = []

        while time.monotonic() < deadline:
            if self.process is None:
                break
            if self.process.poll() is None:
                last_seen_children = self._snapshot_process_children(parent_pid)
                time.sleep(0.25)
                continue

            alive_children = self._filter_alive_pids(last_seen_children)
            return {
                "grace_seconds": grace_seconds,
                "parent_pid": parent_pid,
                "parent_exited_within_window": True,
                "detached_wrapper_suspected": len(alive_children) > 0,
                "observed_children": last_seen_children,
                "alive_children": alive_children,
            }

        return {
            "grace_seconds": grace_seconds,
            "parent_pid": parent_pid,
            "parent_exited_within_window": False,
            "detached_wrapper_suspected": False,
            "observed_children": last_seen_children,
            "alive_children": [],
        }

    @staticmethod
    def _terminate_pid_list(process_data):
        for proc in process_data:
            pid = proc.get("pid")
            if not isinstance(pid, int):
                continue
            try:
                psutil.Process(pid).kill()
            except NoSuchProcess:
                continue
            except Exception:
                logger.warning("Failed to terminate process %s", pid, exc_info=True)

    def _apply_wrapper_policy(self, user_id, user_lang, forge_install=False):
        policy_mode = self._get_wrapper_policy_mode()
        affinity_enforced = bool(self._active_cpu_affinity)
        memory_limit_enforced = self._active_memory_limit_mib > 0
        resource_controls_enforced = affinity_enforced or memory_limit_enforced
        effective_policy_mode = "enforce" if resource_controls_enforced else policy_mode
        if effective_policy_mode == "disabled" or self.process is None:
            return True

        inspection = self._inspect_wrapper_process_shape(self.process.pid)
        if not inspection["detached_wrapper_suspected"]:
            return True

        self._log_launch_event(
            "wrapper_policy_detected",
            level=logging.WARNING,
            policy_mode=policy_mode,
            effective_policy_mode=effective_policy_mode,
            affinity_enforced=affinity_enforced,
            memory_limit_enforced=memory_limit_enforced,
            parent_pid=inspection["parent_pid"],
            grace_seconds=inspection["grace_seconds"],
            detected_process_tree=inspection["alive_children"],
        )

        if effective_policy_mode == "audit":
            return True

        self._terminate_pid_list(inspection["alive_children"])
        self._log_launch_event(
            "launch_failure",
            level=logging.ERROR,
            reason="unsupported_wrapper_shape",
            effective_policy_mode=effective_policy_mode,
            affinity_enforced=affinity_enforced,
            memory_limit_enforced=memory_limit_enforced,
            parent_pid=inspection["parent_pid"],
            grace_seconds=inspection["grace_seconds"],
            detected_process_tree=inspection["alive_children"],
        )
        self.cleanup_server_object()
        self._notify_start_error(
            user_id,
            user_lang,
            "Unsupported wrapper command shape (fork-and-exit) detected.",
        )
        if forge_install:
            self.stats_helper.finish_import()
        return False

    @callback
    def start_server(self, user_id, forge_install=False):
        # Clear cached game port so it's recomputed from current config
        self._game_port_cache = None

        if not user_id:
            user_lang = self.helper.get_setting("language")
        else:
            user_lang = HelperUsers.get_user_lang_by_id(user_id)
        self._active_launch_command = []
        self._active_cpu_affinity = ""
        self._active_memory_limit_mib = 0
        self._active_memory_limit_bytes = 0
        self._active_memory_cgroup_path = ""

        # Checks if user is currently attempting to move global server
        # dir
        if self.helper.dir_migration:
            self._log_launch_event(
                "launch_blocked",
                level=logging.WARNING,
                reason="dir_migration_in_progress",
            )
            WebSocketManager().broadcast_user(
                user_id,
                "send_error",
                {
                    "error": self.helper.translation.translate(
                        "error",
                        "migration",
                        user_lang,
                    )
                },
            )
            return False

        if self.stats_helper.get_import_status() and not forge_install:
            self._log_launch_event(
                "launch_blocked",
                level=logging.WARNING,
                reason="import_in_progress",
            )
            if user_id:
                WebSocketManager().broadcast_user(
                    user_id,
                    "send_error",
                    {
                        "error": self.helper.translation.translate(
                            "error", "not-downloaded", user_lang
                        )
                    },
                )
            return False

        logger.info(
            f"Start command detected. Reloading settings from DB for server {self.name}"
        )
        self.setup_server_run_command()
        self._active_launch_command = list(self.server_command or [])
        self._active_cpu_affinity = ""
        self._active_memory_limit_mib = 0
        self._active_memory_limit_bytes = 0
        self._active_memory_cgroup_path = ""
        # fail safe in case we try to start something already running
        if self.check_running():
            logger.error("Server is already running - Cancelling Startup")
            Console.error("Server is already running - Cancelling Startup")
            self._log_launch_event(
                "launch_blocked",
                level=logging.WARNING,
                reason="already_running",
            )
            self._notify_start_error(user_id, user_lang, "Server is already running.")
            return False
        if self.check_update():
            logger.error("Server is updating. Terminating startup.")
            self._log_launch_event(
                "launch_blocked",
                level=logging.WARNING,
                reason="update_in_progress",
            )
            self._notify_start_error(
                user_id, user_lang, "Server is updating. Startup was denied."
            )
            return False

        if not self._prepare_memory_limit_policy(user_id, user_lang):
            if forge_install:
                self.stats_helper.finish_import()
            return False

        launch_command = self._resolve_launch_command(user_id, user_lang)
        if launch_command is None:
            if forge_install:
                self.stats_helper.finish_import()
            return False

        logger.info(f"Launching Server {self.name} with command {launch_command}")
        Console.info(f"Launching Server {self.name} with command {launch_command}")
        server_type = HelperServers.get_server_type_by_id(self.server_id)

        # Checks for eula. Creates one if none detected.
        # If EULA is detected and not set to true we offer to set it true.
        e_flag = False
        if Helpers.check_file_exists(os.path.join(self.settings["path"], "eula.txt")):
            with open(
                os.path.join(self.settings["path"], "eula.txt"), "r", encoding="utf-8"
            ) as f:
                line = f.readline().lower()
                e_flag = line in [
                    "eula=true",
                    "eula = true",
                    "eula= true",
                    "eula =true",
                ]
        # If this is a forge installer we're running we can bypass the eula checks.
        if forge_install is True:
            e_flag = True
        if not e_flag and self.settings["type"] == "minecraft-java":
            self._log_launch_event(
                "launch_blocked",
                level=logging.WARNING,
                reason="eula_not_accepted",
            )
            if user_id:
                WebSocketManager().broadcast_user(
                    user_id, "send_eula_bootbox", {"id": self.server_id}
                )
            else:
                logger.error(
                    "Autostart failed due to EULA being false. "
                    "Agree not sent due to auto start."
                )
            return False
        if Helpers.is_os_windows():
            logger.info("Windows Detected")
        else:
            logger.info("Unix Detected")

        logger.info(
            f"Starting server in {self.server_path} with command: {self.server_command}"
        )

        if (
            not Helpers.is_os_windows()
            and server_type == "minecraft-bedrock"
        ):
            launch_branch = "bedrock_unix"
            logger.info(
                f"Bedrock and Unix detected for server {self.name}. "
                f"Switching to appropriate execution string"
            )
            my_env = os.environ
            my_env["LD_LIBRARY_PATH"] = self.server_path
            self._log_launch_event(
                "launch_attempt",
                branch=launch_branch,
                env_overrides=["LD_LIBRARY_PATH"],
            )
            try:
                self.process = self._launch_server_process(command=launch_command, env=my_env)
                self._log_launch_event(
                    "launch_spawned",
                    branch=launch_branch,
                    pid=self.process.pid,
                )
            except Exception as ex:
                logger.error(
                    f"Server {self.name} failed to start with error code: {ex}"
                )
                self._log_launch_event(
                    "launch_failure",
                    level=logging.ERROR,
                    reason="spawn_exception",
                    branch=launch_branch,
                    error=str(ex),
                )
                self._notify_start_error(user_id, user_lang, str(ex))
                if forge_install:
                    # Reset import status if failed while forge installing
                    self.stats_helper.finish_import()
                return False
        # ***********************************************
        # ***********************************************
        #               STEAM SERVERS
        # ***********************************************
        # ***********************************************
        elif server_type == "steam_cmd":
            launch_branch = "steam_cmd"
            my_env = os.environ
            env_mod = False
            if Helpers.check_file_exists(Path(self.server_path, "env.json")):
                with open(
                    Path(self.server_path, "env.json"), "r", encoding="utf-8"
                ) as env_file:
                    env_file_data = json.load(env_file)
                    for key, value in env_file_data.items():
                        if "path" in key.lower():
                            items_validated = []
                            for item in value["contents"]:
                                try:
                                    p = Helpers.validate_traversal(
                                        self.server_path, item
                                    )
                                except ValueError:
                                    logger.warning(
                                        "Path traversal detected on server {self.server_id} for env {k} value {i}, skipping"
                                    )
                                p = str(p).replace(":", "\\:")
                                items_validated.append(p)
                            if my_env.get(key, None):
                                if value["mode"] == "append":
                                    items_validated.insert(0, my_env[key])
                                elif value["mode"] == "prepend":
                                    items_validated.append(my_env[key])
                            my_env[key] = ":".join(items_validated)
                        else:
                            items = value["contents"]
                            if value["mode"] == "append":
                                items.insert(0, my_env[key])
                            elif value["mode"] == "prepend":
                                items.append(my_env[key])
                            my_env[key] = ",".join(items)
                    env_mod = True
            if env_mod:
                logger.debug(
                    "Launching process for server %s with modified environment %s",
                    self.server_id,
                    my_env,
                )
            else:
                logger.debug(
                    "Launching process for server %s with un-modified environment",
                    self.server_id,
                )
            self._log_launch_event(
                "launch_attempt",
                branch=launch_branch,
                env_modified=env_mod,
            )
            try:
                self.process = self._launch_server_process(command=launch_command, env=my_env)
                self._log_launch_event(
                    "launch_spawned",
                    branch=launch_branch,
                    pid=self.process.pid,
                )
            except Exception as ex:
                logger.error(
                    f"Server {self.name} failed to start with error code: {ex}"
                )
                self._log_launch_event(
                    "launch_failure",
                    level=logging.ERROR,
                    reason="spawn_exception",
                    branch=launch_branch,
                    error=str(ex),
                )
                self._notify_start_error(
                    user_id, user_lang, str(ex), channel="send_start_error"
                )
                return False

        else:
            launch_branch = "default"
            logger.debug(
                "Starting server %s with unknown type %s",
                self.server_id,
                server_type,
            )
            self._log_launch_event("launch_attempt", branch=launch_branch)
            try:
                self.process = self._launch_server_process(command=launch_command)
                self._log_launch_event(
                    "launch_spawned",
                    branch=launch_branch,
                    pid=self.process.pid,
                )
            except Exception as ex:
                # Checks for java on initial fail
                if not self.helper.detect_java():
                    self._log_launch_event(
                        "launch_failure",
                        level=logging.ERROR,
                        reason="java_not_found",
                        branch=launch_branch,
                        error=str(ex),
                    )
                    if user_id:
                        WebSocketManager().broadcast_user(
                            user_id,
                            "send_error",
                            {
                                "error": self.helper.translation.translate(
                                    "error", "noJava", user_lang
                                ).format(self.name)
                            },
                        )
                    return False
                logger.error(
                    f"Server {self.name} failed to start with error code: {ex}"
                )
                self._log_launch_event(
                    "launch_failure",
                    level=logging.ERROR,
                    reason="spawn_exception",
                    branch=launch_branch,
                    error=str(ex),
                )
                self._notify_start_error(user_id, user_lang, str(ex))
                if forge_install:
                    # Reset import status if failed while forge installing
                    self.stats_helper.finish_import()
                return False

        if not self._attach_process_to_memory_cgroup(user_id, user_lang, forge_install):
            return False

        self._log_effective_memory_limit_state()
        self._log_effective_cpu_affinity_state()

        if not self._apply_wrapper_policy(user_id, user_lang, forge_install):
            return False

        out_buf = ServerOutBuf(self.helper, self.process, self.server_id)

        logger.debug(f"Starting virtual terminal listener for server {self.name}")
        threading.Thread(
            target=out_buf.check, daemon=True, name=f"{self.server_id}_virtual_terminal"
        ).start()

        self.is_crashed = False
        self.stats_helper.server_crash_reset()

        self.start_time = str(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

        if self.process.poll() is None:
            logger.info(f"Server {self.name} running with PID {self.process.pid}")
            Console.info(f"Server {self.name} running with PID {self.process.pid}")
            self._log_launch_event(
                "launch_success",
                pid=self.process.pid,
            )
            self.is_crashed = False
            self.stats_helper.server_crash_reset()
            self.record_server_stats()
            check_internet_thread = threading.Thread(
                target=self.check_internet_thread,
                daemon=True,
                args=(
                    user_id,
                    user_lang,
                ),
                name=f"{self.name}_Internet",
            )
            check_internet_thread.start()
            # Checks if this is the servers first run.
            if self.stats_helper.get_first_run():
                self.stats_helper.set_first_run()
                loc_server_port = self.stats_helper.get_server_stats()["server_port"]
                # Sends port reminder message.
                WebSocketManager().broadcast_user(
                    user_id,
                    "send_error",
                    {
                        "error": self.helper.translation.translate(
                            "error", "portReminder", user_lang
                        ).format(self.name, loc_server_port)
                    },
                )
                server_users = PermissionsServers.get_server_user_list(self.server_id)
                for user in server_users:
                    if user != user_id:
                        WebSocketManager().broadcast_user(user, "send_start_reload", {})
            else:
                server_users = PermissionsServers.get_server_user_list(self.server_id)
                for user in server_users:
                    WebSocketManager().broadcast_user(user, "send_start_reload", {})
        else:
            logger.warning(
                f"Server PID {self.process.pid} died right after starting "
                f"- is this a server config issue?"
            )
            Console.critical(
                f"Server PID {self.process.pid} died right after starting "
                f"- is this a server config issue?"
            )
            self._log_launch_event(
                "launch_failure",
                level=logging.ERROR,
                reason="early_exit_after_spawn",
                pid=self.process.pid,
            )
            self._notify_start_error(
                user_id,
                user_lang,
                "Process exited immediately after launch.",
            )

        if self.settings["crash_detection"]:
            logger.info(
                f"Server {self.name} has crash detection enabled "
                f"- starting watcher task"
            )
            Console.info(
                f"Server {self.name} has crash detection enabled "
                f"- starting watcher task"
            )

            self.server_scheduler.add_job(
                self.detect_crash, "interval", seconds=30, id=f"c_{self.server_id}"
            )

        # If this is a forge install we'll call the watcher to do the things
        if forge_install:
            self.forge_install_watcher()

    def check_internet_thread(self, user_id, user_lang):
        if user_id:
            if not Helpers.check_internet():
                WebSocketManager().broadcast_user(
                    user_id,
                    "send_error",
                    {
                        "error": self.helper.translation.translate(
                            "error", "internet", user_lang
                        )
                    },
                )

    def forge_install_watcher(self):
        # Enter for install if that parameter is true
        while True:
            # We'll watch the process
            if self.process.poll() is None:
                # IF process still has not exited we'll keep looping
                time.sleep(5)
                Console.debug("Installing Forge...")
            else:
                # Process has exited. Lets do some work to setup the new
                # run command.
                # Let's grab the server object we're going to update.
                server_obj: Servers = HelperServers.get_server_obj(self.server_id)

                # The forge install is done so we can delete that install file.
                os.remove(os.path.join(server_obj.path, server_obj.executable))

                # We need to grab the exact forge version number.
                # We know we can find it here in the run.sh/bat script.
                try:
                    # Getting the forge version from the executable command
                    version = re.findall(
                        r"(?:forge|neoforge)-installer-([0-9\.]+)((?:)|"
                        r"(?:-([0-9\.]+)-[a-zA-Z]+)).jar",
                        server_obj.execution_command,
                    )
                    version_info = re.findall(
                        r"(forge|neoforge)-installer-([0-9\.]+)((?:)|"
                        r"(?:-([0-9\.]+)-[a-zA-Z]+)).jar",
                        server_obj.execution_command,
                    )
                    version_param = version_info[0][1].split(".")
                    version_major = int(version_param[0])
                    version_minor = int(version_param[1])
                    if len(version_param) > 2:
                        version_sub = int(version_param[2])
                    else:
                        version_sub = 0

                    # Checking which version we are with
                    if version_major <= 1 and version_minor < 17:
                        # OLD VERSION < 1.17

                        # Retrieving the executable jar filename
                        file_path = glob.glob(
                            f"{server_obj.path}/"
                            f"{version_info[0][0]}-{version[0][1]}*.jar"
                        )[0]
                        file_name = re.findall(
                            r"(forge[-0-9.]+.jar)",
                            file_path,
                        )[0]

                        # Let's set the proper server executable
                        server_obj.executable = os.path.join(file_name)

                        # Get memory values
                        memory_values = re.findall(
                            r"-Xms([A-Z0-9\.]+) -Xmx([A-Z0-9\.]+)",
                            server_obj.execution_command,
                        )

                        # Now lets set up the new run command.
                        # This is based off the run.sh/bat that
                        # Forge uses in 1.17 and <
                        execution_command = (
                            f"java -Xms{memory_values[0][0]} -Xmx{memory_values[0][1]}"
                            f' -jar "{file_name}" nogui'
                        )
                        server_obj.execution_command = execution_command
                        Console.debug(SUCCESSMSG)

                    elif (
                        version_major <= 1 and version_minor <= 20 and version_sub < 3
                    ) or version_info[0][0] == "neoforge":
                        # NEW VERSION >= 1.17 and <= 1.20.2
                        # (no jar file in server dir, only run.bat and run.sh)

                        run_file_path = ""
                        if self.helper.is_os_windows():
                            run_file_path = os.path.join(server_obj.path, "run.bat")
                        else:
                            run_file_path = os.path.join(server_obj.path, "run.sh")

                        if Helpers.check_file_perms(run_file_path) and os.path.isfile(
                            run_file_path
                        ):
                            run_file = open(run_file_path, "r", encoding="utf-8")
                            run_file_text = run_file.read()
                        else:
                            Console.error(
                                "ERROR ! Forge install can't read the scripts files."
                                " Aborting ..."
                            )
                            return

                        # We get the server command parameters from forge script
                        server_command = re.findall(
                            r"java @([a-zA-Z0-9_\.]+)"
                            r" @([a-z./\-]+)"
                            r"([0-9.\-]+(?:-[a-zA-Z0-9]+)?)"
                            r"\/\b([a-z_0-9]+\.txt)\b"
                            r"( .{2,4})?",
                            run_file_text,
                        )[0]

                        version = server_command[2]
                        executable_path = f"{server_command[1]}{server_command[2]}/"
                        # Let's set the proper server executable
                        server_obj.executable = os.path.join(
                            f"{executable_path}{version_info[0][0]}-{version}"
                            "-server.jar"
                        )
                        # Now lets set up the new run command.
                        # This is based off the run.sh/bat that
                        # Forge uses in 1.17 and <
                        execution_command = (
                            f"java @{server_command[0]}"
                            f" @{executable_path}{server_command[3]} nogui"
                            f" {server_command[4]}"
                        )
                        server_obj.execution_command = execution_command
                        Console.debug(SUCCESSMSG)
                    else:
                        # NEW VERSION >= 1.20.3
                        # (executable jar is back in server dir)

                        # Retrieving the executable jar filename
                        file_path = glob.glob(
                            f"{server_obj.path}/forge-{version[0][0]}*.jar"
                        )[0]
                        file_name = re.findall(
                            r"(forge-[\-0-9.]+-shim.jar)",
                            file_path,
                        )[0]

                        # Let's set the proper server executable
                        server_obj.executable = os.path.join(file_name)

                        # Get memory values
                        memory_values = re.findall(
                            r"-Xms([A-Z0-9\.]+) -Xmx([A-Z0-9\.]+)",
                            server_obj.execution_command,
                        )

                        # Now lets set up the new run command.
                        # This is based off the run.sh/bat that
                        # Forge uses in 1.17 and <
                        execution_command = (
                            f"java -Xms{memory_values[0][0]} -Xmx{memory_values[0][1]}"
                            f' -jar "{file_name}" nogui'
                        )
                        server_obj.execution_command = execution_command
                        Console.debug(SUCCESSMSG)
                except:
                    logger.debug("Could not find run file.")
                    # TODO Use regex to get version and rebuild simple execution

                # We'll update the server with the new information now.
                HelperServers.update_server(server_obj)
                self.stats_helper.finish_import()
                server_users = PermissionsServers.get_server_user_list(self.server_id)

                for user in server_users:
                    WebSocketManager().broadcast_user(user, "send_start_reload", {})
                break

    def stop_crash_detection(self):
        # This is only used if the crash detection settings change
        # while the server is running.
        if self.check_running():
            logger.info(f"Detected crash detection shut off for server {self.name}")
            try:
                self.server_scheduler.remove_job("c_" + str(self.server_id))
            except:
                logger.error(
                    f"Removing crash watcher for server {self.name} failed. "
                    f"Assuming it was never started."
                )

    def start_crash_detection(self):
        # This is only used if the crash detection settings change
        # while the server is running.
        if self.check_running():
            logger.info(
                f"Server {self.name} has crash detection enabled "
                f"- starting watcher task"
            )
            Console.info(
                f"Server {self.name} has crash detection enabled "
                "- starting watcher task"
            )
            try:
                self.server_scheduler.add_job(
                    self.detect_crash, "interval", seconds=30, id=f"c_{self.server_id}"
                )
            except:
                logger.info(f"Job with id c_{self.server_id} already running...")

    def stop_threaded_server(self):
        self.stop_server()

        if self.server_thread:
            self.server_thread.join()

    @callback
    def stop_server(self):
        running = self.check_running()
        if not running:
            logger.info(f"Can't stop server {self.name} if it's not running")
            Console.info(f"Can't stop server {self.name} if it's not running")
            return
        if self.settings["crash_detection"]:
            # remove crash detection watcher
            logger.info(f"Removing crash watcher for server {self.name}")
            try:
                self.server_scheduler.remove_job("c_" + str(self.server_id))
            except:
                logger.error(
                    f"Removing crash watcher for server {self.name} failed. "
                    f"Assuming it was never started."
                )
        if self.settings["stop_command"]:
            logger.info(f"Stop command requested for {self.settings['server_name']}.")
            self.send_command(self.settings["stop_command"])
            self.write_player_cache()
        else:
            # windows will need to be handled separately for Ctrl+C
            self.process.terminate()
        i = 0

        # caching the name and pid number
        server_name = self.name
        server_pid = self.process.pid
        self.shutdown_timeout = self.settings["shutdown_timeout"]

        while running:
            i += 1
            ttk = int(self.shutdown_timeout - (i * 2))
            if i <= self.shutdown_timeout / 2:
                logstr = (
                    f"Server {server_name} is still running "
                    "- waiting 2s to see if it stops"
                    f"({ttk} "
                    f"seconds until force close)"
                )
                logger.info(logstr)
                Console.info(logstr)
            running = self.check_running()
            time.sleep(2)

            # if we haven't closed in 60 seconds, let's just slam down on the PID
            if i >= round(self.shutdown_timeout / 2, 0):
                logger.info(
                    f"Server {server_name} is still running - Forcing the process down"
                )
                Console.info(
                    f"Server {server_name} is still running - Forcing the process down"
                )
                self.kill()

        logger.info(f"Stopped Server {server_name} with PID {server_pid}")
        Console.info(f"Stopped Server {server_name} with PID {server_pid}")

        # massive resetting of variables
        self.cleanup_server_object()
        server_users = PermissionsServers.get_server_user_list(self.server_id)

        try:
            # remove the stats polling job since server is stopped
            logger.info("Cleaning up stats schedules for server %s", self.server_id)
            self.server_scheduler.remove_job("stats_" + str(self.server_id))
            self.server_scheduler.remove_job("save_stats_" + str(self.server_id))
        except JobLookupError as e:
            logger.error(
                f"Could not remove job with id stats_{self.server_id} due"
                + f" to error: {e}"
            )
        self.record_server_stats()

        for user in server_users:
            WebSocketManager().broadcast_user(user, "send_start_reload", {})

    def restart_threaded_server(self, user_id):
        if self.is_backingup:
            logger.info(
                "Restart command detected. Supressing - server has"
                " backup shutdown enabled and server is currently backing up."
            )
            return
        # if not already running, let's just start
        if not self.check_running():
            self.run_threaded_server(user_id)
        else:
            logger.info(
                f"Restart command detected. Sending stop command to {self.server_id}."
            )
            self.stop_threaded_server()
            time.sleep(2)
            self.run_threaded_server(user_id)

    def cleanup_server_object(self):
        self.start_time = None
        self.restart_count = 0
        self.is_crashed = False
        self.updating = False
        self.process = None
        self._active_cpu_affinity = ""
        self._active_memory_limit_mib = 0
        self._active_memory_limit_bytes = 0
        self._active_memory_cgroup_path = ""

    def check_running(self):
        # if process is None, we never tried to start
        if self.process is None:
            return False
        poll = self.process.poll()
        if poll is None:
            return True
        self.last_rc = poll
        return False

    @callback
    def send_command(self, command):
        if not self.check_running() and command.lower() != "start":
            logger.warning(f'Server not running, unable to send command "{command}"')
            return False
        Console.info(f"COMMAND TIME: {command}")
        logger.debug(f"Sending command {command} to server")

        # send it
        self.process.stdin.write(f"{command}\n".encode("utf-8"))
        self.process.stdin.flush()
        return True

    @callback
    def crash_detected(self, name):
        # clear the old scheduled watcher task
        self.server_scheduler.remove_job(f"c_{self.server_id}")
        # remove the stats polling job since server is stopped
        self.server_scheduler.remove_job("stats_" + str(self.server_id))
        self.server_scheduler.remove_job("save_stats_" + str(self.server_id))

        # the server crashed, or isn't found - so let's reset things.
        logger.warning(
            f"The server {name} seems to have vanished unexpectedly, did it crash?"
        )

        if self.settings["crash_detection"]:
            logger.warning(
                f"The server {name} has crashed and will be restarted. "
                f"Restarting server"
            )
            Console.critical(
                f"The server {name} has crashed and will be restarted. "
                f"Restarting server"
            )

            self.run_threaded_server(None)
            return True
        logger.critical(
            f"The server {name} has crashed, "
            f"crash detection is disabled and it will not be restarted"
        )
        Console.critical(
            f"The server {name} has crashed, "
            f"crash detection is disabled and it will not be restarted"
        )
        return False

    @callback
    def kill(self):
        logger.info(f"Terminating server {self.server_id} and all child processes")
        try:
            process = psutil.Process(self.process.pid)
        except NoSuchProcess:
            logger.info(f"Cannot kill {self.process.pid} as we cannot find that pid.")
            return
        # for every sub process...
        for proc in process.children(recursive=True):
            # kill all the child processes
            logger.info(f"Sending SIGKILL to server {proc.name}")
            proc.kill()
        # kill the main process we are after
        logger.info("Sending SIGKILL to parent")
        try:
            self.server_scheduler.remove_job("stats_" + str(self.server_id))
        except JobLookupError as e:
            logger.error(
                f"Could not remove job with id stats_{self.server_id} due"
                + f" to error: {e}"
            )
        self.process.kill()

    def get_start_time(self):
        return self.start_time if self.check_running() else False

    def get_pid(self):
        return self.process.pid if self.process is not None else None

    def detect_crash(self):
        logger.info(f"Detecting possible crash for server: {self.name} ")

        running = self.check_running()

        # if all is okay, we set the restart count to 0 and just exit out
        if running:
            Console.debug("Successfully found process. Resetting crash counter to 0")
            self.restart_count = 0
            return
        # check the exit code -- This could be a fix for /stop
        if str(self.process.returncode) in self.settings["ignored_exits"].split(","):
            logger.warning(
                f"Process {self.process.pid} exited with code "
                f"{self.process.returncode}. This is considered a clean exit"
                f" supressing crash handling."
            )
            # cancel the watcher task
            self.server_scheduler.remove_job("c_" + str(self.server_id))
            self.server_scheduler.remove_job("stats_" + str(self.server_id))
            return

        self.stats_helper.sever_crashed()
        # if we haven't tried to restart more 3 or more times
        if self.restart_count <= 3:
            # start the server if needed
            server_restarted = self.crash_detected(self.name)

            if server_restarted:
                # add to the restart count
                self.restart_count = self.restart_count + 1

        # we have tried to restart 4 times...
        elif self.restart_count == 4:
            logger.critical(
                f"Server {self.name} has been restarted {self.restart_count}"
                f" times. It has crashed, not restarting."
            )
            Console.critical(
                f"Server {self.name} has been restarted {self.restart_count}"
                f" times. It has crashed, not restarting."
            )

            self.restart_count = 0
            self.is_crashed = True
            self.stats_helper.sever_crashed()

            # cancel the watcher task
            self.server_scheduler.remove_job("c_" + str(self.server_id))

    def remove_watcher_thread(self):
        logger.info("Removing old crash detection watcher thread")
        Console.info("Removing old crash detection watcher thread")
        self.server_scheduler.remove_job("c_" + str(self.server_id))

    def agree_eula(self, user_id):
        eula_file = os.path.join(self.server_path, "eula.txt")
        with open(eula_file, "w", encoding="utf-8") as f:
            f.write("eula=true")
        self.run_threaded_server(user_id)

    def server_restore_threader(self, backup_id, backup_file, in_place=False):
        # import the server again based on zipfile
        backup_config = HelpersManagement.get_backup_config(backup_id)

        # This path gets resolved and checked for traversal before restore_starter
        # so that it remains async.
        # At this point this path cannot be trusted.
        backup_type = backup_config.get("backup_type", "zip_vault")
        if backup_type == "zip_vault":
            expected_backup_location = Path(
                backup_config["backup_location"], backup_config["backup_id"]
            )
        else:
            expected_backup_location = Path(
                backup_config["backup_location"], "snapshot_backups", "manifests"
            )

        expected_backup_location = expected_backup_location.resolve()

        try:
            Helpers.validate_traversal(expected_backup_location, backup_file)
        except ValueError as why:
            # Crash out on possible traversal.
            logger.error(
                f"Possible backup traversal detected on restore request: {why}",
            )

            server_users = PermissionsServers.get_server_user_list(self.server_id)
            for user in server_users:
                WebSocketManager().broadcast_user(
                    user,
                    "send_error",
                    self.helper.translation.translate(
                        "notify", "restoreFailed", HelperUsers.get_user_lang_by_id(user)
                    ),
                )
            return

        backup_location = (expected_backup_location / backup_file).resolve()

        restore_thread = threading.Thread(
            target=self.backup_mgr.restore_starter,
            daemon=True,
            name=f"backup_{backup_config['backup_id']}",
            args=[backup_config, backup_location, self, in_place],
        )

        restore_thread.start()

    def server_backup_threader(self, backup_id=None, update=False):
        backup_config = self.get_backup_config(backup_id)
        # Check to see if we're already backing up
        if self.check_backup_by_id(backup_config["backup_id"]):
            return False

        if backup_config["before"]:
            logger.debug(
                "Found running server and send command option. Sending command"
            )
            self.send_command(backup_config["before"])
            # Pause to let command run
            time.sleep(5)

        self.was_running = False
        if backup_config["shutdown"]:
            logger.info(
                "Found shutdown preference. Delaying"
                + "backup start. Shutting down server."
            )
            if not update:
                if self.check_running():
                    self.stop_server()
                    self.was_running = True

        backup_thread = threading.Thread(
            target=self.backup_server,
            daemon=True,
            name=f"backup_{backup_config['backup_id']}",
            args=[backup_config["backup_id"]],
        )
        logger.info(
            f"Starting Backup Thread for server {self.settings['server_name']}."
        )
        if self.server_path is None:
            self.server_path = Helpers.get_os_understandable_path(self.settings["path"])
            logger.info(
                "Backup Thread - Local server path not defined. "
                "Setting local server path variable."
            )

        try:
            backup_thread.start()
        except Exception as ex:
            logger.error(f"Failed to start backup: {ex}")
            return False
        logger.info(f"Backup Thread started for server {self.settings['server_name']}.")

    @callback
    def backup_server(self, backup_id) -> dict | bool:
        logger.info(f"Starting server {self.name} (ID {self.server_id}) backup")
        server_users = PermissionsServers.get_server_user_list(self.server_id)
        # Alert the start of the backup to the authorized users.
        for user in server_users:
            WebSocketManager().broadcast_user(
                user,
                "notification",
                self.helper.translation.translate(
                    "notify", "backupStarted", HelperUsers.get_user_lang_by_id(user)
                ).format(self.name),
            )
        time.sleep(3)

        conf = HelpersManagement.get_backup_config(backup_id)
        # Adjust the location to include the backup ID for destination.
        backup_location = os.path.join(conf["backup_location"], conf["backup_id"])

        # Check if the backup location even exists.
        if not backup_location:
            Console.critical("No backup path found. Canceling")
            backup_status = json.loads(
                HelpersManagement.get_backup_config(backup_id)["status"]
            )
            if backup_status["status"] == "Failed":
                last_backup_status = "❌"
                reason = backup_status["message"]
                return {
                    "backup_status": last_backup_status,
                    "backup_error": reason,
                }
        if conf["before"]:
            logger.debug(
                "Found running server and send command option. Sending command"
            )
            self.send_command(conf["before"])
            # Pause to let command run
            time.sleep(5)
        backup_name, backup_size = self.backup_mgr.backup_starter(conf, self)
        if conf["after"]:
            self.send_command(conf["after"])
        if conf["shutdown"] and self.was_running:
            logger.info(
                "Backup complete. User had shutdown preference. Starting server."
            )
            self.run_threaded_server(HelperUsers.get_user_id_by_name("system"))
        self.set_backup_status()

        # Return data for webhooks callback
        base_url = f"{self.helper.get_setting('base_url')}"
        size = backup_size
        backup_status = json.loads(
            HelpersManagement.get_backup_config(backup_id)["status"]
        )
        reason = backup_status["message"]
        if not backup_name:
            return {
                "backup_status": "❌",
                "backup_error": reason,
            }
        if backup_size:
            size = self.helper.human_readable_file_size(backup_size)
        url = (
            f"https://{base_url}/api/v2/servers/{self.server_id}"
            f"/backups/backup/{backup_id}/download/{html.escape(backup_name)}"
        )
        if conf["backup_type"] == "snapshot":
            size = 0
            url = (
                f"https://{base_url}/panel/edit_backup?"
                f"id={self.server_id}&backup_id={backup_id}"
            )
        backup_status = json.loads(
            HelpersManagement.get_backup_config(backup_id)["status"]
        )
        last_backup_status = "✅"
        reason = ""
        if backup_status["status"] == "Failed":
            last_backup_status = "❌"
            reason = backup_status["message"]
        return {
            "backup_name": backup_name,
            "backup_size": size,
            "backup_link": url,
            "backup_status": last_backup_status,
            "backup_error": reason,
        }

    def set_backup_status(self):
        backups = HelpersManagement.get_backups_by_server(self.server_id, True)
        alert = False
        for backup in backups:
            if json.loads(backup.status)["status"] == "Failed":
                alert = True
        self.last_backup_failed = alert

    def last_backup_status(self):
        return self.last_backup_failed

    @callback
    def server_upgrade(self):
        self.stats_helper.set_update(True)
        update_thread = threading.Thread(
            target=self.threaded_jar_update, daemon=True, name=f"exe_update_{self.name}"
        )
        update_thread.start()

    def write_player_cache(self):
        write_json = {}
        for item in self.player_cache:
            write_json[item["name"]] = item
        with open(
            os.path.join(
                self.helper.root_dir,
                "app",
                "config",
                "db",
                "servers",
                self.server_id,
                "players_cache.json",
            ),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(json.dumps(write_json, indent=4))
            logger.info("Cache file refreshed")

    def get_formatted_server_players(self) -> list:
        server_players = self.get_server_players()
        if len(server_players) == 0:
            return []
        if isinstance(server_players[0], dict):
            sp = server_players.copy()
            server_players = []
            for player in sp:
                server_players.append(player["Name"])
        return server_players

    def cache_players(self):
        if not self.check_running():
            return
        server_players = self.get_formatted_server_players()
        for p in self.player_cache[:]:
            if p["status"] == "Online" and p["name"] not in server_players:
                p["status"] = "Offline"
                p["last_seen"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
            elif p["name"] in server_players:
                self.player_cache.remove(p)
        for player in server_players:
            if player == "Anonymous Player":
                # Skip Anonymous Player
                continue
            if player in self.player_cache:
                self.player_cache.remove(player)
            self.player_cache.append(
                {
                    "name": player,
                    "status": "Online",
                    "last_seen": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                }
            )

    def check_update(self):
        return self.stats_helper.get_server_stats()["updating"]

    def threaded_jar_update(self):
        server_users = PermissionsServers.get_server_user_list(self.server_id)
        # check to make sure a backup config actually exists before starting the update
        if len(self.management_helper.get_backups_by_server(self.server_id, True)) <= 0:
            for user in server_users:
                WebSocketManager().broadcast_user(
                    user,
                    "notification",
                    "Backup config does not exist for "
                    + self.name
                    + ". canceling update.",
                )
            logger.error(f"Back config does not exist for {self.name}. Update Failed.")
            self.stats_helper.set_update(False)
            return
        was_started = "-1"

        ###############################
        # Backup Server ###############
        ###############################

        # Get default backup configuration
        backup_config = HelpersManagement.get_default_server_backup(self.server_id)
        # start threaded backup
        self.server_backup_threader(backup_config["backup_id"], True)

        # checks if server is running. Calls shutdown if it is running.
        if self.check_running():
            was_started = True
            logger.info(
                f"Server with PID {self.process.pid} is running. "
                f"Sending shutdown command"
            )
            self.stop_threaded_server()
        else:
            was_started = False
        ws_params = {
            "isUpdating": self.check_update(),
            "server_id": self.server_id,
            "wasRunning": was_started,
        }
        if len(WebSocketManager().clients) > 0:
            # There are clients
            self.check_update()
            message = (
                '<a data-id="' + str(self.server_id) + '" class=""> UPDATING...</i></a>'
            )
            ws_params["string"] = message
        for user in server_users:
            WebSocketManager().broadcast_user_page(
                "/panel/server_detail", user, "update_button_status", ws_params
            )
        current_executable = os.path.join(
            Helpers.get_os_understandable_path(self.settings["path"]),
            self.settings["executable"],
        )
        backing_up = True
        # wait for backup
        while backing_up:
            # Check to see if we're already backing up
            backing_up = self.check_backup_by_id(backup_config["backup_id"])
            time.sleep(2)

        # check if backup was successful
        backup_status = json.loads(
            HelpersManagement.get_backup_config(backup_config["backup_id"])["status"]
        )["status"]
        if backup_status == "Failed":
            for user in server_users:
                WebSocketManager().broadcast_user(
                    user,
                    "notification",
                    "Backup failed for " + self.name + ". canceling update.",
                )
            self.stats_helper.set_update(False)
            return
        server_type = HelperServers.get_server_type_by_id(self.server_id)
        # lets download the files
        if server_type == "minecraft-java":
            jar_dir = os.path.dirname(current_executable)
            jar_file_name = os.path.basename(current_executable)

            downloaded = FileHelpers.ssl_get_file(
                self.settings["executable_update_url"], jar_dir, jar_file_name
            )
        elif self.server_object.type == "hytale":
            self.import_helper.download_install_hytale(self.server_path, self.server_id)
            downloaded = True
        # SteamCMD #####################
        elif HelperServers.get_server_type_by_id(self.server_id) == "steam_cmd":
            try:
                # Set our storage locations
                steamcmd_path = os.path.join(self.settings["path"], "steamcmd_files")
                gamefiles_path = os.path.join(self.settings["path"], "gameserver_files")
                app_id = SteamCMD.find_app_id(gamefiles_path)

                # Ensure game and steam directories exist in server directory.
                self.helper.ensure_dir_exists(steamcmd_path)
                self.helper.ensure_dir_exists(gamefiles_path)

                # Set the SteamCMD install directory for next install.
                self.steam = SteamCMD(steamcmd_path)

                # Install the game server files.
                self.steam.app_update(app_id, gamefiles_path, validate=True)
                downloaded = True
            except ValueError as e:
                logger.critical(
                    f"Failed to update SteamCMD Server \n App ID find failed: \n{e}"
                )
                downloaded = False
            except Exception as e:
                logger.critical(f"Failed to update SteamCMD Server \n{e}")
                downloaded = False
        else:  # Bedrock if nothing else
            # downloads zip from remote url
            downloaded = False
            try:
                bedrock_url = Helpers.get_latest_bedrock_url()
                if bedrock_url:
                    # Use the new method for secure download
                    self.import_helper.download_threaded_bedrock_server(
                        self.settings["path"], self.server_id, bedrock_url, True
                    )
                    downloaded = True
            except Exception as e:
                logger.critical(
                    f"Failed to download bedrock executable for update \n{e}"
                )

        ################################
        # Start Upgraded Server ########
        ################################

        if downloaded:
            logger.info("Executable updated successfully. Starting Server")

            self.stats_helper.set_update(False)
            if len(WebSocketManager().clients) > 0:
                # There are clients
                self.check_update()
                for user in server_users:
                    WebSocketManager().broadcast_user(
                        user,
                        "notification",
                        "Executable update finished for " + self.name,
                    )
                # sleep so first notif can completely run
                time.sleep(3)
            for user in server_users:
                WebSocketManager().broadcast_user_page(
                    "/panel/server_detail",
                    user,
                    "update_button_status",
                    {
                        "isUpdating": self.check_update(),
                        "server_id": self.server_id,
                        "wasRunning": was_started,
                    },
                )
                WebSocketManager().broadcast_user_page(
                    user, "/panel/dashboard", "send_start_reload", {}
                )
            self.management_helper.add_to_audit_log_raw(
                "Alert",
                "-1",
                self.server_id,
                "Executable update finished for " + self.name,
                self.settings["server_ip"],
            )
            if was_started:
                self.run_threaded_server(HelperUsers.get_user_id_by_name("system"))
        else:
            for user in server_users:
                WebSocketManager().broadcast_user(
                    user,
                    "notification",
                    "Executable update failed for "
                    + self.name
                    + ". Check log file for details.",
                )
            logger.error("Executable download failed.")
            self.stats_helper.set_update(False)
        self.check_server_version()  # Check to make sure the update was
        # successful and that we match remote
        for user in server_users:
            WebSocketManager().broadcast_user(
                user,
                "remove_spinner",
                {"server_id": self.server_id},
            )

    def check_server_version(self):
        if not self.settings.get("update_watcher"):
            logger.debug("User has update watcher turned off. Killing out of function")
            self.update_available = False
            return
        current_hash = self.helper.crypto_helper.calculate_file_hash_sha256(
            str(
                Path(
                    str(self.settings.get("path")),
                    str(self.settings.get("executable")),
                )
            )
        )
        url_pattern = (
            r"^https:\/\/(www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}"
            r"(\/[a-zA-Z0-9-._~:/?#\[\]@!$&'()*+,;=]*)?$"
        )
        try:  # Get hash from Big Bucket remote
            if re.match(
                url_pattern,
                str(self.server_object.executable_update_url),
            ):
                response = requests.get(
                    f"{self.server_object.executable_update_url}.sha256", timeout=1
                )
            else:
                self.update_available = False
                return logger.error(
                    "Server version check failed. Invalid url: %s",
                    self.server_object.executable_update_url,
                )
        except TimeoutError as why:
            self.update_available = False
            return logger.error("Could not capture remote URL hash with error %s", why)
        remote_hash = None
        if response.status_code == 200:
            remote_hash = response.text

        if remote_hash != current_hash:  # Compare hashes
            self.update_available = True
        else:
            self.update_available = False

    def start_dir_calc_task(self):
        server_dt = HelperServers.get_server_data_by_id(self.server_id)
        self.server_size = Helpers.human_readable_file_size(
            self.file_helper.get_dir_size(server_dt["path"])
        )
        self.dir_scheduler.add_job(
            self.calc_dir_size,
            "interval",
            minutes=self.helper.get_setting("dir_size_poll_freq_minutes"),
            id=str(self.server_id) + "_dir_poll",
        )
        self.dir_scheduler.add_job(
            self.cache_players,
            "interval",
            seconds=5,
            id=str(self.server_id) + "_players_poll",
        )

    def calc_dir_size(self):
        server_dt = HelperServers.get_server_data_by_id(self.server_id)
        self.server_size = Helpers.human_readable_file_size(
            self.file_helper.get_dir_size(server_dt["path"])
        )

    # **********************************************************************************
    #                               Minecraft Servers Statistics
    # **********************************************************************************

    def realtime_stats(self):
        # only get stats if clients are connected.
        # no point in burning cpu
        if len(WebSocketManager().clients) > 0:
            total_players = 0
            max_players = 0
            servers_ping = []
            raw_ping_result = []
            raw_ping_result = self.get_raw_server_stats(self.server_id)

            if f"{raw_ping_result.get('icon')}" == "b''":
                raw_ping_result["icon"] = False

            servers_ping.append(
                {
                    "id": raw_ping_result.get("id"),
                    "started": raw_ping_result.get("started"),
                    "running": raw_ping_result.get("running"),
                    "cpu": raw_ping_result.get("cpu"),
                    "cpu_capacity_cores": raw_ping_result.get("cpu_capacity_cores", 0),
                    "mem": raw_ping_result.get("mem"),
                    "mem_capacity": raw_ping_result.get("mem_capacity"),
                    "mem_capacity_raw": raw_ping_result.get("mem_capacity_raw"),
                    "mem_percent": raw_ping_result.get("mem_percent"),
                    "world_name": raw_ping_result.get("world_name"),
                    "world_size": raw_ping_result.get("world_size"),
                    "server_port": raw_ping_result.get("server_port"),
                    "game_port": raw_ping_result.get("game_port"),
                    "int_ping_results": raw_ping_result.get("int_ping_results"),
                    "online": raw_ping_result.get("online"),
                    "max": raw_ping_result.get("max"),
                    "players": raw_ping_result.get("players"),
                    "desc": raw_ping_result.get("desc"),
                    "version": raw_ping_result.get("version"),
                    "icon": raw_ping_result.get("icon"),
                    "telemetry_tps": raw_ping_result.get("telemetry_tps", False),
                    "telemetry_mspt": raw_ping_result.get("telemetry_mspt", False),
                    "crashed": self.is_crashed,
                    "count_players": self.server_object.count_players,
                    "server_notes": self.server_object.server_notes,
                }
            )

            WebSocketManager().broadcast_page_params(
                "/panel/server_detail",
                {"id": str(self.server_id)},
                "update_server_details",
                {
                    "id": raw_ping_result.get("id"),
                    "started": raw_ping_result.get("started"),
                    "running": raw_ping_result.get("running"),
                    "cpu": raw_ping_result.get("cpu"),
                    "cpu_capacity_cores": raw_ping_result.get("cpu_capacity_cores", 0),
                    "mem": raw_ping_result.get("mem"),
                    "mem_raw": raw_ping_result.get("mem_raw"),
                    "mem_capacity": raw_ping_result.get("mem_capacity"),
                    "mem_capacity_raw": raw_ping_result.get("mem_capacity_raw"),
                    "mem_percent": raw_ping_result.get("mem_percent"),
                    "world_name": raw_ping_result.get("world_name"),
                    "world_size": raw_ping_result.get("world_size"),
                    "server_port": raw_ping_result.get("server_port"),
                    "int_ping_results": raw_ping_result.get("int_ping_results"),
                    "online": raw_ping_result.get("online"),
                    "max": raw_ping_result.get("max"),
                    "players": raw_ping_result.get("players"),
                    "desc": raw_ping_result.get("desc"),
                    "version": raw_ping_result.get("version"),
                    "icon": raw_ping_result.get("icon"),
                    "telemetry_tps": raw_ping_result.get("telemetry_tps", False),
                    "telemetry_mspt": raw_ping_result.get("telemetry_mspt", False),
                    "crashed": self.is_crashed,
                    "created": datetime.datetime.now().strftime("%Y/%m/%d, %H:%M:%S"),
                    "players_cache": self.player_cache,
                    "server_notes": self.server_object.server_notes,
                },
            )
            total_players += int(raw_ping_result.get("online"))
            max_players += int(raw_ping_result.get("max"))

            # self.record_server_stats()

            if len(servers_ping) > 0:
                try:
                    WebSocketManager().broadcast_page(
                        "/panel/dashboard", "update_server_status", servers_ping
                    )
                except:
                    Console.critical("Can't broadcast server status to websocket")

    def check_backup_by_id(self, backup_id: str) -> bool:
        # Check to see if we're already backing up
        for thread in threading.enumerate():
            if thread.getName() == f"backup_{backup_id}":
                Console.debug(f"Backup with id {backup_id} already running!")
                return True
        return False

    def _get_game_port(self, server_type, server_port, server_path, execution_command):
        """Derive the game port from server config, cached per server lifecycle.

        The monitoring/query port stored in the DB may differ from the port
        players actually connect to. The result is cached and cleared on
        server start/stop.
        """
        if self._game_port_cache is not None:
            return self._game_port_cache

        game_port = server_port

        match server_type:
            case "hytale":
                # Try to parse --bind 0.0.0.0:<port> from the execution command
                if execution_command:
                    bind_match = re.search(r"--bind\s+[\d.]+:(\d+)", execution_command)
                    if bind_match:
                        game_port = int(bind_match.group(1))
                    else:
                        # Fallback: Hytale query port is game port + 3
                        game_port = server_port - 3
                else:
                    game_port = server_port - 3

            case "minecraft-java":
                # Try to read server-port from server.properties
                properties_path = os.path.join(server_path, "server.properties")
                try:
                    with open(properties_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("server-port="):
                                game_port = int(line.split("=", 1)[1].strip())
                                break
                except FileNotFoundError:
                    logger.warning(
                        "server.properties not found at %s for server %s"
                        " — unable to parse game port",
                        properties_path,
                        self.server_id,
                    )
                except (ValueError, OSError) as e:
                    logger.warning(
                        "Failed to parse game port from %s for server %s: %s",
                        properties_path,
                        self.server_id,
                        e,
                    )

        self._game_port_cache = game_port
        return game_port

    def _get_mod_telemetry(self, host, telemetry_port):
        """Fetch optional telemetry endpoint exposed by a server-side mod."""
        normalized_port = normalize_telemetry_port(telemetry_port)
        if normalized_port == 0:
            return {
                "telemetry_tps": False,
                "telemetry_mspt": False,
                "telemetry_players": [],
            }

        telemetry_url = build_telemetry_url(host, normalized_port)
        try:
            response = requests.get(telemetry_url, timeout=1)
            if response.status_code != 200:
                logger.debug(
                    "Telemetry query returned non-200 for server %s: %s",
                    self.server_id,
                    response.status_code,
                )
                return {
                    "telemetry_tps": False,
                    "telemetry_mspt": False,
                    "telemetry_players": [],
                }

            return parse_telemetry_payload(response.json())
        except (
            requests.RequestException,
            ValueError,
            json.decoder.JSONDecodeError,
        ) as ex:
            logger.debug("Telemetry query failed for server %s: %s", self.server_id, ex)
            return {
                "telemetry_tps": False,
                "telemetry_mspt": False,
                "telemetry_players": [],
            }

    def get_backup_config(self, backup_id) -> dict:
        if not backup_id:
            return HelpersManagement.get_default_server_backup(self.server_id)
        return HelpersManagement.get_backup_config(backup_id)

    def _get_memory_capacity_bytes(self):
        try:
            configured_limit_mib = canonicalize_memory_limit_mib(
                self.settings.get("memory_limit_mib", 0)
            )
        except MemoryLimitValidationError:
            configured_limit_mib = 0
        if configured_limit_mib > 0:
            return configured_limit_mib * 1024 * 1024
        return int(psutil.virtual_memory().total)

    def _get_memory_capacity_human(self):
        return Helpers.human_readable_file_size(self._get_memory_capacity_bytes())

    def get_servers_stats(self):
        server_type = HelperServers.get_server_type_by_id(self.server_id)
        server_stats = {}

        server_id = self.server_id
        logger.debug("Getting Stats for Server %s | %s...", self.name, server_id)
        server = HelperServers.get_server_data_by_id(server_id)

        # get our server object, settings and data dictionaries
        self.reload_server_settings()
        memory_capacity_bytes = self._get_memory_capacity_bytes()

        # process stats
        p_stats = Stats._try_get_process_stats(
            self.process,
            self.check_running(),
            memory_capacity_bytes=memory_capacity_bytes,
        )
        process_memory_capacity = p_stats.get("memory_capacity_raw", 0)
        if not isinstance(process_memory_capacity, (int, float)) or process_memory_capacity <= 0:
            process_memory_capacity = memory_capacity_bytes
        internal_ip = server["server_ip"]
        server_port = server["server_port"]
        server_name = server.get("server_name", f"ID#{server_id}")
        game_port = self._get_game_port(
            server_type,
            server_port,
            server.get("path", ""),
            server.get("execution_command", ""),
        )
        running = self.check_running()
        telemetry_data = (
            self._get_mod_telemetry(internal_ip, server.get("telemetry_port", 0))
            if running
            else {
                "telemetry_tps": False,
                "telemetry_mspt": False,
                "telemetry_players": [],
            }
        )

        logger.debug(f"Pinging server '{server}' on {internal_ip}:{server_port}")
        if server_type in ("minecraft-bedrock", "raknet"):
            int_mc_ping = ping_raknet(internal_ip, int(server_port))
        elif server_type == "hytale":
            int_mc_ping = NitradoPing.ping(internal_ip, server_port)
        else:
            try:
                int_mc_ping = ping(internal_ip, int(server_port))
            except:
                int_mc_ping = False

        int_data = False
        ping_data = {}

        # if we got a good ping return, let's parse it
        if int_mc_ping:
            int_data = True
            if server_type == "minecraft-bedrock":
                ping_data = Stats.parse_server_raknet_ping(int_mc_ping)
            elif server_type == "hytale":
                ping_data = NitradoPing.parse_ping_response(int_mc_ping)
            else:
                ping_data = Stats.parse_server_ping(int_mc_ping)
        # Makes sure we only show stats when a server is online
        # otherwise people have gotten confused.
        if running:
            server_stats = {
                "id": server_id,
                "started": self.get_start_time(),
                "running": running,
                "cpu": p_stats.get("cpu_usage", 0),
                "cpu_capacity_cores": p_stats.get("cpu_capacity_cores", 0),
                "mem": p_stats.get("memory_usage", 0),
                "mem_raw": p_stats.get("memory_usage_raw", 0),
                "mem_percent": p_stats.get("mem_percentage", 0),
                "mem_capacity": Helpers.human_readable_file_size(process_memory_capacity),
                "mem_capacity_raw": process_memory_capacity,
                "world_name": server_name,
                "world_size": self.server_size,
                "server_port": server_port,
                "game_port": game_port,
                "int_ping_results": int_data,
                "online": ping_data.get("online", False),
                "max": ping_data.get("max", False),
                "players": ping_data.get("players", False),
                "desc": ping_data.get("server_description", False),
                "version": ping_data.get("server_version", False),
                "icon": ping_data.get("server_icon"),
                "telemetry_tps": telemetry_data.get("telemetry_tps", False),
                "telemetry_mspt": telemetry_data.get("telemetry_mspt", False),
            }
        else:
            server_stats = {
                "id": server_id,
                "started": self.get_start_time(),
                "running": running,
                "cpu": p_stats.get("cpu_usage", 0),
                "cpu_capacity_cores": p_stats.get("cpu_capacity_cores", 0),
                "mem": p_stats.get("memory_usage", 0),
                "mem_raw": p_stats.get("memory_usage_raw", 0),
                "mem_percent": p_stats.get("mem_percentage", 0),
                "mem_capacity": Helpers.human_readable_file_size(process_memory_capacity),
                "mem_capacity_raw": process_memory_capacity,
                "world_name": server_name,
                "world_size": self.server_size,
                "server_port": server_port,
                "game_port": game_port,
                "int_ping_results": int_data,
                "online": False,
                "max": False,
                "players": False,
                "desc": False,
                "version": False,
                "icon": None,
                "telemetry_tps": False,
                "telemetry_mspt": False,
            }

        return server_stats

    def get_server_players(self):
        server = HelperServers.get_server_data_by_id(self.server_id)
        server_type = HelperServers.get_server_type_by_id(self.server_id)
        logger.debug(f"Getting players for server {server['server_name']}")

        internal_ip = server["server_ip"]
        server_port = server["server_port"]

        logger.debug(f"Pinging {internal_ip} on port {server_port}")
        if server_type == "minecraft-java":
            int_mc_ping = ping(internal_ip, int(server_port))

            ping_data = {}

            # if we got a good ping return, let's parse it
            if int_mc_ping:
                ping_data = Stats.parse_server_ping(int_mc_ping)
                return ping_data["players"]
        elif server_type == "hytale":
            return NitradoPing.parse_ping_response(
                NitradoPing.ping(internal_ip, server_port)
            ).get("players", [])

        return []

    def get_raw_server_stats(self, server_id):
        server_type = HelperServers.get_server_type_by_id(server_id)
        int_data = False
        ping_data = {}

        try:
            server = HelperServers.get_server_obj(server_id)
        except:
            return {
                "id": server_id,
                "started": False,
                "running": False,
                "cpu": 0,
                "cpu_capacity_cores": 0,
                "mem": 0,
                "mem_capacity": 0,
                "mem_capacity_raw": 0,
                "mem_percent": 0,
                "world_name": None,
                "world_size": None,
                "server_port": None,
                "game_port": None,
                "int_ping_results": False,
                "online": False,
                "max": False,
                "players": False,
                "desc": False,
                "version": False,
                "icon": False,
                "telemetry_tps": False,
                "telemetry_mspt": False,
            }

        server_stats = {}
        if not server:
            return {}
        server_dt = HelperServers.get_server_data_by_id(server_id)

        logger.debug(f"Getting stats for server: {server_id}")

        # get our server object, settings and data dictionaries
        self.reload_server_settings()
        memory_capacity_bytes = self._get_memory_capacity_bytes()

        # world data
        server_name = server_dt["server_name"]

        # process stats
        p_stats = Stats._try_get_process_stats(
            self.process,
            self.check_running(),
            memory_capacity_bytes=memory_capacity_bytes,
        )
        process_memory_capacity = p_stats.get("memory_capacity_raw", 0)
        if not isinstance(process_memory_capacity, (int, float)) or process_memory_capacity <= 0:
            process_memory_capacity = memory_capacity_bytes

        internal_ip = server_dt["server_ip"]
        server_port = server_dt["server_port"]
        game_port = self._get_game_port(
            server_type,
            server_port,
            server_dt.get("path", ""),
            server_dt.get("execution_command", ""),
        )
        running = self.check_running()
        telemetry_data = (
            self._get_mod_telemetry(internal_ip, server_dt.get("telemetry_port", 0))
            if running
            else {
                "telemetry_tps": False,
                "telemetry_mspt": False,
                "telemetry_players": [],
            }
        )

        logger.debug(f"Pinging server '{self.name}' on {internal_ip}:{server_port}")
        if HelperServers.get_server_type_by_id(server_id) in (
            "minecraft-bedrock",
            "raknet",
        ):
            int_mc_ping = ping_raknet(internal_ip, int(server_port))
            if int_mc_ping:
                ping_data = Stats.parse_server_raknet_ping(int_mc_ping)
                int_data = True
        elif server_type == "hytale":
            int_mc_ping = NitradoPing.ping(internal_ip, server_port)
            if int_mc_ping:
                int_data = True
            ping_data = NitradoPing.parse_ping_response(int_mc_ping)
        else:
            int_mc_ping = ping(internal_ip, int(server_port))
            if int_mc_ping:
                ping_data = Stats.parse_server_ping(int_mc_ping)
                int_data = True
        # Makes sure we only show stats when a server is online
        # otherwise people have gotten confused.
        if running:
            server_stats = {
                "id": server_id,
                "started": self.get_start_time(),
                "running": running,
                "cpu": p_stats.get("cpu_usage", 0),
                "cpu_capacity_cores": p_stats.get("cpu_capacity_cores", 0),
                "mem": p_stats.get("memory_usage", 0),
                "mem_raw": p_stats.get("memory_usage_raw", 0),
                "mem_percent": p_stats.get("mem_percentage", 0),
                "mem_capacity": Helpers.human_readable_file_size(process_memory_capacity),
                "mem_capacity_raw": process_memory_capacity,
                "world_name": server_name,
                "world_size": self.server_size,
                "server_port": server_port,
                "game_port": game_port,
                "int_ping_results": int_data,
                "online": ping_data.get("online", False),
                "max": ping_data.get("max", False),
                "players": ping_data.get("players", False),
                "desc": ping_data.get("server_description", False),
                "version": ping_data.get("server_version", False),
                "icon": ping_data.get("server_icon", False),
                "telemetry_tps": telemetry_data.get("telemetry_tps", False),
                "telemetry_mspt": telemetry_data.get("telemetry_mspt", False),
            }
        else:
            server_stats = {
                "id": server_id,
                "started": self.get_start_time(),
                "running": running,
                "cpu": p_stats.get("cpu_usage", 0),
                "cpu_capacity_cores": p_stats.get("cpu_capacity_cores", 0),
                "mem": p_stats.get("memory_usage", 0),
                "mem_raw": p_stats.get("memory_usage_raw", 0),
                "mem_percent": p_stats.get("mem_percentage", 0),
                "mem_capacity": Helpers.human_readable_file_size(process_memory_capacity),
                "mem_capacity_raw": process_memory_capacity,
                "world_name": server_name,
                "world_size": self.server_size,
                "server_port": server_port,
                "game_port": game_port,
                "int_ping_results": int_data,
                "online": False,
                "max": False,
                "players": False,
                "desc": False,
                "version": False,
                "icon": False,
                "telemetry_tps": False,
                "telemetry_mspt": False,
            }

        return server_stats

    def record_server_stats(self):
        server_stats = self.get_servers_stats()
        self.stats_helper.insert_server_stats(server_stats)

        self.cpu_usage.labels(f"{self.server_id}").set(server_stats.get("cpu"))
        self.mem_usage_percent.labels(f"{self.server_id}").set(
            server_stats.get("mem_percent")
        )
        self.minecraft_version.labels(f"{self.server_id}").info(
            {"version": f"{server_stats.get('version')}"}
        )
        self.online_players.labels(f"{self.server_id}").set(server_stats.get("online"))

        # delete old data
        max_age = self.helper.get_setting("history_max_age")
        now = datetime.datetime.now()
        minimum_to_exist = now - datetime.timedelta(days=max_age)

        self.stats_helper.remove_old_stats(minimum_to_exist)

    def init_registries(self):
        # REGISTRY Entries for Server Stats functions
        self.cpu_usage = Gauge(
            name="CPU_Usage",
            documentation="The CPU usage of the server",
            labelnames=["server_id"],
            registry=self.server_registry,
        )
        self.mem_usage_percent = Gauge(
            name="Mem_Usage",
            documentation="The Memory usage of the server",
            labelnames=["server_id"],
            registry=self.server_registry,
        )
        self.minecraft_version = Info(
            name="Minecraft_Version",
            documentation="The version of the minecraft of this server",
            labelnames=["server_id"],
            registry=self.server_registry,
        )

        self.online_players = Gauge(
            name="online_players",
            documentation="The number of players online for a server",
            labelnames=["server_id"],
            registry=self.server_registry,
        )

    def get_server_history(self):
        history = self.stats_helper.get_history_stats(self.server_id, 1)
        return history

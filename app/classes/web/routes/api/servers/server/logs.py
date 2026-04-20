import html
import gzip
import logging
import math
import pathlib
import re
import typing as t
from app.classes.models.server_permissions import EnumPermissionsServer
from app.classes.shared.server import ServerOutBuf
from app.classes.web.base_api_handler import BaseApiHandler

logger = logging.getLogger(__name__)

ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class ApiServersServerLogsHandler(BaseApiHandler):
    DEFAULT_PAGE_SIZE = 200
    MAX_PAGE_SIZE = 2000
    MAX_LISTED_LOGS = 1000
    LOG_FILE_SUFFIXES = {".log", ".txt", ".out", ".gz"}

    def _server_root_path(self, server_data: t.Dict[str, t.Any]) -> pathlib.Path:
        return pathlib.Path(server_data["path"]).resolve(strict=False)

    def _relative_log_path(
        self, server_root: pathlib.Path, log_path: pathlib.Path
    ) -> str:
        try:
            return log_path.resolve(strict=False).relative_to(server_root).as_posix()
        except ValueError:
            return log_path.name

    def _resolve_log_source(
        self, server_data: t.Dict[str, t.Any], source_path: str
    ) -> pathlib.Path:
        server_root = self._server_root_path(server_data)
        requested_source = str(source_path or "").strip() or str(server_data["log_path"])
        resolved = pathlib.Path(
            self.helper.validate_traversal(str(server_root), requested_source)
        )
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"Unable to find file to tail: {resolved}")
        return resolved

    @staticmethod
    def _iter_log_lines(log_path: pathlib.Path):
        if log_path.suffix.lower() == ".gz":
            open_fn = gzip.open
        else:
            open_fn = open

        with open_fn(log_path, "rt", encoding="utf-8", errors="ignore") as log_file:
            for line in log_file:
                yield line.rstrip("\r\n")

    def _list_available_logs(self, server_data: t.Dict[str, t.Any]) -> t.List[dict]:
        server_root = self._server_root_path(server_data)
        try:
            configured_log_path = pathlib.Path(
                self._resolve_log_source(server_data, str(server_data["log_path"]))
            )
        except Exception:
            configured_log_path = (server_root / "logs" / "latest.log").resolve(
                strict=False
            )

        candidate_dirs = {
            configured_log_path.parent.resolve(strict=False),
            (server_root / "logs").resolve(strict=False),
            (server_root / "crash-reports").resolve(strict=False),
            (server_root / "kubejs" / "logs").resolve(strict=False),
        }

        found: t.Dict[str, dict] = {}
        for log_dir in candidate_dirs:
            if not log_dir.exists() or not log_dir.is_dir():
                continue
            for file_path in log_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in self.LOG_FILE_SUFFIXES:
                    continue
                rel_path = self._relative_log_path(server_root, file_path)
                stat = file_path.stat()
                found[rel_path] = {
                    "path": rel_path,
                    "name": file_path.name,
                    "size": int(stat.st_size),
                    "modified": int(stat.st_mtime),
                }

        logs = list(found.values())
        logs.sort(key=lambda item: item.get("modified", 0), reverse=True)
        return logs[: self.MAX_LISTED_LOGS]

    def _paginate_log_file(
        self, log_path: pathlib.Path, page: int, page_size: int, query: str
    ) -> t.Tuple[t.List[str], int, int]:
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        query_normalized = (query or "").strip().lower()

        page_lines: t.List[str] = []
        total_lines = 0
        for line in self._iter_log_lines(log_path):
            if query_normalized and query_normalized not in line.lower():
                continue

            if start_index <= total_lines < end_index:
                page_lines.append(line)
            total_lines += 1

        total_pages = max(1, math.ceil(total_lines / page_size)) if total_lines else 1
        return page_lines, total_lines, total_pages

    def get(self, server_id: str):
        auth_data = self.authenticate_user()
        if not auth_data:
            return

        # GET /api/v2/servers/server/logs?file=true
        read_log_file = self.get_query_argument("file", None) == "true"
        # GET /api/v2/servers/server/logs?colors=true
        colored_output = self.get_query_argument("colors", None) == "true"
        # GET /api/v2/servers/server/logs?raw=true
        disable_ansi_strip = self.get_query_argument("raw", None) == "true"
        # GET /api/v2/servers/server/logs?html=true
        use_html = self.get_query_argument("html", None) == "true"
        # GET /api/v2/servers/server/logs?list=true
        list_sources = self.get_query_argument("list", None) == "true"

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
        if EnumPermissionsServer.LOGS not in server_permissions:
            # if the user doesn't have Logs permission, return an error
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

        server_data = self.controller.servers.get_server_data_by_id(server_id)
        server_root = self._server_root_path(server_data)

        if read_log_file and list_sources:
            sources = self._list_available_logs(server_data)
            try:
                active_path = self._resolve_log_source(server_data, "")
                active_source = self._relative_log_path(server_root, active_path)
            except Exception:
                active_source = str(server_data.get("log_path", ""))
            return self.finish_json(
                200,
                {"status": "ok", "data": sources, "active_source": active_source},
            )

        if read_log_file:
            requested_source = self.get_query_argument("source", "")
            try:
                log_source_path = self._resolve_log_source(server_data, requested_source)
            except ValueError as ex:
                return self.finish_json(
                    400,
                    {
                        "status": "error",
                        "error": "INVALID_PATH",
                        "error_data": str(ex),
                    },
                )
            except FileNotFoundError as ex:
                return self.finish_json(
                    404,
                    {
                        "status": "error",
                        "error": "LOG_NOT_FOUND",
                        "error_data": str(ex),
                    },
                )

            pagination_requested = any(
                self.get_query_argument(arg, None) is not None
                for arg in ("page", "page_size", "query", "full")
            )

            if pagination_requested:
                try:
                    page = int(self.get_query_argument("page", 1))
                    page_size = int(
                        self.get_query_argument("page_size", self.DEFAULT_PAGE_SIZE)
                    )
                except ValueError:
                    return self.finish_json(
                        400,
                        {
                            "status": "error",
                            "error": "INVALID_PAGINATION",
                            "error_data": "Page and page size must be integers.",
                        },
                    )

                page = max(1, page)
                page_size = min(max(1, page_size), self.MAX_PAGE_SIZE)
                query = self.get_query_argument("query", "")

                try:
                    raw_lines, total_lines, total_pages = self._paginate_log_file(
                        log_source_path, page, page_size, query
                    )
                except OSError as ex:
                    return self.finish_json(
                        500,
                        {
                            "status": "error",
                            "error": "LOG_READ_ERROR",
                            "error_data": str(ex),
                        },
                    )
            else:
                log_lines = self.helper.get_setting("max_log_lines")
                raw_lines = self.helper.tail_file(log_source_path, log_lines)
                raw_lines = [line.rstrip("\r\n") for line in raw_lines]
                total_lines = len(raw_lines)
                total_pages = 1
                page = 1
                page_size = len(raw_lines)
                query = ""
        else:
            raw_lines = ServerOutBuf.lines.get(server_id, [])
            total_lines = len(raw_lines)
            total_pages = 1
            page = 1
            page_size = len(raw_lines)
            query = ""
            log_source_path = None

        lines = []

        for line in raw_lines:
            try:
                if not disable_ansi_strip:
                    line = ansi_escape.sub("", line)
                    line = re.sub("[A-z]{2}\b\b", "", line)
                    line = html.escape(line)

                if colored_output:
                    line = self.helper.log_colors(line)

                lines.append(line)
            except Exception as e:
                logger.warning(f"Skipping Log Line due to error: {e}")

        if use_html:
            lines = [f"{line}<br />" for line in lines]

        response: t.Dict[str, t.Any] = {"status": "ok", "data": lines}
        if read_log_file:
            response["pagination"] = {
                "page": page,
                "page_size": page_size,
                "total_lines": total_lines,
                "total_pages": total_pages,
                "query": query,
                "source": (
                    self._relative_log_path(server_root, log_source_path)
                    if log_source_path is not None
                    else str(server_data.get("log_path", ""))
                ),
            }

        self.finish_json(200, response)

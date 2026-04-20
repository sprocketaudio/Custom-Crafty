import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SERVER_FILE = PROJECT_ROOT / "app" / "classes" / "shared" / "server.py"
TASKS_FILE = PROJECT_ROOT / "app" / "classes" / "shared" / "tasks.py"


def _parse_python_file(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _get_class_method(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for class_item in node.body:
                if isinstance(class_item, ast.FunctionDef) and class_item.name == method_name:
                    return class_item
    raise AssertionError(f"Unable to find {class_name}.{method_name} in AST.")


def _get_attribute_calls(function_node: ast.FunctionDef, attr_name: str) -> list[ast.Call]:
    calls = []
    for node in ast.walk(function_node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == attr_name:
                calls.append(node)
    return calls


def test_start_server_uses_only_launch_helper_for_process_spawn():
    tree = _parse_python_file(SERVER_FILE)
    start_server = _get_class_method(tree, "ServerInstance", "start_server")

    direct_popen_calls = _get_attribute_calls(start_server, "Popen")
    launch_helper_calls = _get_attribute_calls(start_server, "_launch_server_process")

    assert (
        len(direct_popen_calls) == 0
    ), "start_server should not directly call subprocess.Popen."
    assert len(launch_helper_calls) == 3, (
        "Expected one launch-helper call per start branch "
        "(bedrock_unix, steam_cmd, default)."
    )

    for call in launch_helper_calls:
        command_kw = next((kw for kw in call.keywords if kw.arg == "command"), None)
        assert command_kw is not None, "_launch_server_process must receive command=launch_command."
        assert isinstance(command_kw.value, ast.Name)
        assert command_kw.value.id == "launch_command"


def test_restart_and_recovery_paths_reenter_run_threaded_server():
    tree = _parse_python_file(SERVER_FILE)

    expected_min_calls = {
        "restart_threaded_server": 2,
        "crash_detected": 1,
        "backup_server": 1,
        "threaded_jar_update": 1,
    }
    for method_name, min_count in expected_min_calls.items():
        method = _get_class_method(tree, "ServerInstance", method_name)
        run_calls = _get_attribute_calls(method, "run_threaded_server")
        assert len(run_calls) >= min_count, (
            f"{method_name} should call run_threaded_server at least {min_count} time(s) "
            "so launches converge through start_server affinity enforcement."
        )


def test_command_watcher_dispatches_start_and_restart_to_lifecycle_methods():
    tree = _parse_python_file(TASKS_FILE)
    command_watcher = _get_class_method(tree, "TasksManager", "command_watcher")

    dispatch_found = {}
    for node in ast.walk(command_watcher):
        if not isinstance(node, ast.Match):
            continue
        for case in node.cases:
            pattern = case.pattern
            if not (
                isinstance(pattern, ast.MatchValue)
                and isinstance(pattern.value, ast.Constant)
                and isinstance(pattern.value.value, str)
            ):
                continue
            command_name = pattern.value.value
            called_methods = {
                call.func.attr
                for call in ast.walk(ast.Module(body=case.body, type_ignores=[]))
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            }
            dispatch_found[command_name] = called_methods

    assert "run_threaded_server" in dispatch_found.get("start_server", set())
    assert "restart_threaded_server" in dispatch_found.get("restart_server", set())

from types import SimpleNamespace

import pytest

from app.classes.helpers.helpers import Helpers
from app.classes.web.routes.api.crafty.upload.index import ApiFilesUploadHandler


def _handler_for_path_validation(tmp_path, filename: str, *, chunked: bool = False):
    handler = ApiFilesUploadHandler.__new__(ApiFilesUploadHandler)
    handler.filename = filename
    handler.chunked = chunked
    handler.file_id = "upload-123" if chunked else None
    handler.chunk_index = None
    handler.upload_dir = tmp_path / "uploads"
    handler.controller = SimpleNamespace(project_root=tmp_path)
    handler.helper = SimpleNamespace(validate_traversal=Helpers.validate_traversal)
    return handler


def test_upload_path_validation_keeps_regular_and_chunk_paths_in_scope(tmp_path):
    handler = _handler_for_path_validation(tmp_path, "server.jar", chunked=True)

    handler._validate_upload_paths()

    assert handler.temp_dir == (tmp_path / "temp" / "upload-123").resolve()


@pytest.mark.parametrize("filename", ["../outside.jar", "nested/file.jar", ""])
def test_upload_path_validation_rejects_unsafe_filenames(tmp_path, filename):
    handler = _handler_for_path_validation(tmp_path, filename)

    with pytest.raises(ValueError):
        handler._validate_upload_paths()


def test_upload_path_validation_rejects_chunk_id_traversal(tmp_path):
    handler = _handler_for_path_validation(tmp_path, "server.jar", chunked=True)
    handler.file_id = "../outside"

    with pytest.raises(ValueError):
        handler._validate_upload_paths()


def test_upload_path_validation_rejects_non_numeric_chunk_id(tmp_path):
    handler = _handler_for_path_validation(tmp_path, "server.jar", chunked=True)
    handler.chunk_index = "../0"

    with pytest.raises(ValueError):
        handler._validate_upload_paths()

import logging
import os
import shutil
import json
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import nbtlib
except ModuleNotFoundError:
    nbtlib = None


class NbtFileError(Exception):
    """Raised when NBT read/write operations cannot be completed."""


class NbtFileHelpers:
    NBT_MIME = "application/x-minecraft-nbt"
    NBT_BACKUP_SUFFIX = ".crafty-nbt.bak"
    EDITOR_ENCODING_SNBT = "snbt"
    EDITOR_ENCODING_JSON = "nbt_json"

    @staticmethod
    def is_nbt_file(path: str) -> bool:
        return str(path).lower().endswith(".dat")

    @staticmethod
    def is_available() -> bool:
        return nbtlib is not None

    @classmethod
    def can_open_in_editor(cls, path: str) -> bool:
        return cls.is_nbt_file(path) and cls.is_available()

    @staticmethod
    def _guess_is_gzipped(path: str) -> bool:
        with open(path, "rb") as file_handle:
            return file_handle.read(2) == b"\x1f\x8b"

    @classmethod
    def _load_nbt_file(cls, path: str):
        if nbtlib is None:
            raise NbtFileError(
                "NBT editor support is unavailable. Install dependency 'nbtlib'."
            )

        if not Path(path).is_file():
            raise NbtFileError(f"NBT path does not exist or is not a file: {path}")

        guessed_gzipped = cls._guess_is_gzipped(path)
        try:
            return nbtlib.load(path, gzipped=guessed_gzipped)
        except Exception:
            # Some files may not match the header guess; retry once with inverse mode.
            return nbtlib.load(path, gzipped=not guessed_gzipped)

    @classmethod
    def read_as_snbt(cls, path: str) -> str:
        try:
            nbt_file = cls._load_nbt_file(path)
            return nbt_file.snbt(indent=2)
        except Exception as ex:
            raise NbtFileError(str(ex)) from ex

    @classmethod
    def read_as_json(cls, path: str) -> str:
        try:
            nbt_file = cls._load_nbt_file(path)
            unpacked = nbt_file.unpack(json=True)
            return json.dumps(unpacked, indent=2, ensure_ascii=False, sort_keys=True)
        except Exception as ex:
            raise NbtFileError(str(ex)) from ex

    @classmethod
    def get_backup_path(cls, path: str) -> str:
        return f"{path}{cls.NBT_BACKUP_SUFFIX}"

    @classmethod
    def write_from_snbt(
        cls, path: str, snbt_payload: str, create_backup: bool = True
    ) -> str:
        if nbtlib is None:
            raise NbtFileError(
                "NBT editor support is unavailable. Install dependency 'nbtlib'."
            )

        temp_path = f"{path}.crafty-nbt.tmp"
        try:
            existing_nbt = cls._load_nbt_file(path)
            parsed_nbt = nbtlib.parse_nbt(snbt_payload)
            if not isinstance(parsed_nbt, nbtlib.Compound):
                raise NbtFileError("NBT root must be a Compound tag.")
            nbt_file = nbtlib.File(parsed_nbt, root_name=existing_nbt.root_name)
            backup_path = cls.get_backup_path(path)
            if create_backup:
                shutil.copy2(path, backup_path)

            nbt_file.save(
                temp_path,
                gzipped=existing_nbt.gzipped,
                byteorder=existing_nbt.byteorder,
            )
            os.replace(temp_path, path)
            return backup_path if create_backup else ""
        except Exception as ex:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    logger.warning("Unable to clean temporary NBT file: %s", temp_path)
            if isinstance(ex, NbtFileError):
                raise
            raise NbtFileError(str(ex)) from ex

    @classmethod
    def _coerce_tag_with_template(cls, template_tag, value, trace_path: str = "root"):
        if nbtlib is None:
            raise NbtFileError(
                "NBT editor support is unavailable. Install dependency 'nbtlib'."
            )

        if isinstance(template_tag, nbtlib.Compound):
            if not isinstance(value, dict):
                raise NbtFileError(
                    f"Expected object at '{trace_path}' in JSON NBT editor mode."
                )
            template_keys = set(template_tag.keys())
            incoming_keys = set(value.keys())
            unknown_keys = sorted(incoming_keys - template_keys)
            if unknown_keys:
                raise NbtFileError(
                    "JSON NBT mode does not support adding new keys. "
                    f"Unexpected keys at '{trace_path}': {', '.join(unknown_keys[:5])}"
                )
            coerced = {}
            for key, nested_value in value.items():
                coerced[key] = cls._coerce_tag_with_template(
                    template_tag[key], nested_value, f"{trace_path}.{key}"
                )
            return nbtlib.Compound(coerced)

        if isinstance(template_tag, nbtlib.List):
            if not isinstance(value, list):
                raise NbtFileError(
                    f"Expected array at '{trace_path}' in JSON NBT editor mode."
                )
            subtype = template_tag.subtype
            if subtype is nbtlib.tag.End:
                if value:
                    raise NbtFileError(
                        f"Cannot infer list subtype for '{trace_path}'. "
                        "Use raw SNBT mode for this edit."
                    )
                return type(template_tag)([])
            coerced_items = []
            for index, item_value in enumerate(value):
                item_path = f"{trace_path}[{index}]"
                if subtype is nbtlib.Compound:
                    item_template = (
                        template_tag[index]
                        if index < len(template_tag)
                        else (
                            template_tag[0]
                            if len(template_tag) > 0
                            else nbtlib.Compound()
                        )
                    )
                    coerced_items.append(
                        cls._coerce_tag_with_template(
                            item_template,
                            item_value,
                            item_path,
                        )
                    )
                else:
                    try:
                        coerced_items.append(subtype(item_value))
                    except Exception as ex:
                        raise NbtFileError(
                            f"Invalid list item at '{item_path}': {ex}"
                        ) from ex
            return type(template_tag)(coerced_items)

        if isinstance(
            template_tag, (nbtlib.ByteArray, nbtlib.IntArray, nbtlib.LongArray)
        ):
            if not isinstance(value, list):
                raise NbtFileError(
                    f"Expected integer array at '{trace_path}' in JSON NBT mode."
                )
            try:
                return type(template_tag)(value)
            except Exception as ex:
                raise NbtFileError(
                    f"Invalid array payload at '{trace_path}': {ex}"
                ) from ex

        try:
            return type(template_tag)(value)
        except Exception as ex:
            raise NbtFileError(
                f"Invalid value at '{trace_path}' for tag type "
                f"'{type(template_tag).__name__}': {ex}"
            ) from ex

    @classmethod
    def write_from_json(
        cls, path: str, json_payload: str, create_backup: bool = True
    ) -> str:
        if nbtlib is None:
            raise NbtFileError(
                "NBT editor support is unavailable. Install dependency 'nbtlib'."
            )

        try:
            parsed_json = json.loads(json_payload)
        except json.JSONDecodeError as ex:
            raise NbtFileError(f"Invalid JSON: {ex}") from ex

        if not isinstance(parsed_json, dict):
            raise NbtFileError("JSON NBT mode requires a root object.")

        existing_nbt = cls._load_nbt_file(path)
        coerced_root = cls._coerce_tag_with_template(existing_nbt, parsed_json)
        rebuilt = nbtlib.File(coerced_root, root_name=existing_nbt.root_name)
        rebuilt.gzipped = existing_nbt.gzipped
        rebuilt.byteorder = existing_nbt.byteorder
        return cls.write_from_snbt(
            path, rebuilt.snbt(indent=2), create_backup=create_backup
        )

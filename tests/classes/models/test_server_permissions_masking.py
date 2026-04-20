from app.classes.models.server_permissions import EnumPermissionsServer, PermissionsServers


def test_normalize_permissions_mask_pads_legacy_masks() -> None:
    legacy_mask = "11111111"
    normalized = PermissionsServers.normalize_permissions_mask(legacy_mask)
    assert len(normalized) == len(EnumPermissionsServer)
    assert normalized.startswith(legacy_mask)
    assert normalized.endswith("00")


def test_has_permission_handles_short_legacy_masks_without_index_error() -> None:
    legacy_mask = "11111111"
    assert PermissionsServers.has_permission(legacy_mask, EnumPermissionsServer.FILES)
    assert not PermissionsServers.has_permission(
        legacy_mask, EnumPermissionsServer.NBT_READ
    )
    assert not PermissionsServers.has_permission(
        legacy_mask, EnumPermissionsServer.NBT_WRITE
    )


def test_set_permission_expands_mask_before_assignment() -> None:
    mask = PermissionsServers.set_permission(
        "00000000", EnumPermissionsServer.NBT_WRITE, 1
    )
    assert len(mask) == len(EnumPermissionsServer)
    assert mask[EnumPermissionsServer.NBT_WRITE.value] == "1"

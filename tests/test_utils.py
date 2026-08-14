import os
from pathlib import Path
from unittest.mock import patch

from cachecache.utils import has_write_permission, has_space_left, is_writable


class TestHasWritePermission:

    def test_existing_writable_path(self, tmp_path):
        assert has_write_permission(tmp_path) is True

    def test_existing_writable_path_str(self, tmp_path):
        assert has_write_permission(str(tmp_path)) is True

    def test_nonexistent_path_writable_parent(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist"
        assert has_write_permission(nonexistent) is True

    def test_nonexistent_path_nonexistent_parent(self, tmp_path):
        nonexistent = tmp_path / "no_parent" / "no_child"
        # Remove the parent to simulate missing parent
        assert has_write_permission(nonexistent / "deep") is False

    def test_existing_non_writable_path(self, tmp_path):
        readonly = tmp_path / "readonly"
        readonly.mkdir()
        readonly.chmod(0o444)
        try:
            assert has_write_permission(readonly) is False
        finally:
            readonly.chmod(0o755)


class TestHasSpaceLeft:

    def test_existing_path_enough_space(self, tmp_path):
        # 0 MB required should always pass
        assert has_space_left(tmp_path, required_space_mb=0) is True

    def test_existing_path_str(self, tmp_path):
        assert has_space_left(str(tmp_path), required_space_mb=0) is True

    def test_existing_path_huge_requirement(self, tmp_path):
        # Require absurdly large space
        assert has_space_left(tmp_path, required_space_mb=1e12) is False

    def test_nonexistent_path_checks_parent(self, tmp_path):
        nonexistent = tmp_path / "subdir"
        assert has_space_left(nonexistent, required_space_mb=0) is True

    def test_nonexistent_path_nonexistent_parent(self, tmp_path):
        nonexistent = tmp_path / "no_parent" / "no_child" / "deep"
        assert has_space_left(nonexistent) is False


class TestIsWritable:

    def test_writable_with_space(self, tmp_path):
        assert is_writable(tmp_path, required_space_mb=0) is True

    def test_not_writable_no_space(self, tmp_path):
        assert is_writable(tmp_path, required_space_mb=1e12) is False

    def test_not_writable_no_permission(self, tmp_path):
        readonly = tmp_path / "readonly"
        readonly.mkdir()
        readonly.chmod(0o444)
        try:
            assert is_writable(readonly, required_space_mb=0) is False
        finally:
            readonly.chmod(0o755)

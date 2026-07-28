from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from genblaze_core import Asset
from genblaze_core.storage.transfer import AssetTransfer

from app.workspace import current_media_workspace, media_workspace, require_media_workspace


class MediaWorkspaceTests(unittest.TestCase):
    def test_workspace_is_transferable_by_genblaze_and_removed_after_use(self) -> None:
        temporary_root = Path(tempfile.gettempdir()).resolve()
        workspace_path: Path

        self.assertIsNone(current_media_workspace())
        with media_workspace() as workspace_path:
            self.assertEqual(current_media_workspace(), workspace_path)
            self.assertTrue(workspace_path.is_relative_to(temporary_root))
            artifact = workspace_path / "captioned.png"
            artifact.write_bytes(b"captioned-media")

            backend = MagicMock()
            backend.exists.return_value = False
            backend.get_durable_url.side_effect = lambda key: f"https://storage.test/{key}"
            asset = Asset(url=artifact.as_uri(), media_type="image/png")

            AssetTransfer(backend).transfer(asset)

            backend.put.assert_called_once()
            self.assertEqual(asset.sha256, hashlib.sha256(b"captioned-media").hexdigest())
            self.assertTrue(asset.url.startswith("https://storage.test/"))

        self.assertFalse(workspace_path.exists())
        self.assertIsNone(current_media_workspace())

    def test_rejects_workspace_outside_the_system_temporary_directory(self) -> None:
        outside_temp = Path(__file__).resolve().parent

        with self.assertRaisesRegex(ValueError, "system temporary directory"):
            require_media_workspace(outside_temp)


if __name__ == "__main__":
    unittest.main()

"""Setup failure and reuse contracts; no network or real environment mutation."""

import hashlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import bootstrap


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="tennispose space ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.python = self.root / ".venv" / "bin" / "python"
        (self.root / ".venv").mkdir()
        (self.root / "requirements.txt").write_text("example==1.0\n")
        self.model = self.root / "models" / "model.task"
        self.marker = self.root / ".venv" / ".tennispose-requirements.sha256"
        self.patcher = patch.object(bootstrap, "ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_matching_dependencies_do_not_install(self):
        self.marker.write_text(bootstrap.digest(self.root / "requirements.txt"))
        with patch.object(bootstrap, "run") as run:
            bootstrap.ensure_dependencies(self.python, False)
        self.assertFalse(any("install" in call.args[0] for call in run.call_args_list))
        self.assertTrue(any("check" in call.args[0] for call in run.call_args_list))

    def test_failed_install_never_marks_environment_ready(self):
        with patch.object(bootstrap, "run", side_effect=subprocess.CalledProcessError(1, "pip")):
            with self.assertRaises(subprocess.CalledProcessError):
                bootstrap.ensure_dependencies(self.python, False)
        self.assertFalse(self.marker.exists())

    def test_broken_existing_environment_is_preserved(self):
        note = self.root / ".venv" / "keep.txt"
        note.write_text("preserve")
        with self.assertRaisesRegex(RuntimeError, "not deleted"):
            bootstrap.ensure_environment(self.root / ".venv")
        self.assertEqual(note.read_text(), "preserve")

    def test_bad_existing_model_is_preserved_without_network(self):
        self.model.parent.mkdir()
        self.model.write_bytes(b"existing")
        with patch.object(bootstrap.urllib.request, "urlopen") as request:
            with self.assertRaisesRegex(RuntimeError, "not overwritten"):
                bootstrap.ensure_model(self.python, self.model)
        request.assert_not_called()
        self.assertEqual(self.model.read_bytes(), b"existing")

    def test_verified_existing_model_needs_no_network(self):
        self.model.parent.mkdir()
        self.model.write_bytes(b"verified")
        with patch.object(bootstrap, "MODEL_SHA256", hashlib.sha256(b"verified").hexdigest()):
            with patch.object(bootstrap.urllib.request, "urlopen") as request:
                bootstrap.ensure_model(self.python, self.model)
        request.assert_not_called()

    def test_failed_download_checksum_leaves_no_accepted_or_partial_model(self):
        with patch.object(bootstrap, "run", return_value=subprocess.CompletedProcess([], 0, stdout="cert.pem")):
            with patch.object(bootstrap.ssl, "create_default_context"):
                with patch.object(bootstrap.urllib.request, "urlopen", return_value=io.BytesIO(b"truncated")):
                    with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                        bootstrap.ensure_model(self.python, self.model)
        self.assertFalse(self.model.exists())
        self.assertEqual(list(self.model.parent.iterdir()), [])


if __name__ == "__main__":
    unittest.main()

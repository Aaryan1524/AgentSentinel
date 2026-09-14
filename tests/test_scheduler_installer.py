from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import plistlib
import unittest

from agent_sentinel.installers.scheduler import (
    LABEL,
    install_scheduler,
    scheduler_paths,
    uninstall_scheduler,
)


class SchedulerInstallerTests(unittest.TestCase):
    def test_macos_install_is_safe_idempotent_and_removable(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            preview = install_scheduler(home=home, dry_run=True, activate=False, system_name="Darwin")
            self.assertTrue(preview.changed)
            self.assertFalse(preview.paths[0].exists())

            installed = install_scheduler(home=home, activate=False, system_name="Darwin")
            path = installed.paths[0]
            self.assertTrue(installed.changed)
            self.assertEqual(plistlib.loads(path.read_bytes())["Label"], LABEL)
            self.assertFalse(install_scheduler(home=home, activate=False, system_name="Darwin").changed)

            removed = uninstall_scheduler(home=home, deactivate=False, system_name="Darwin")
            self.assertTrue(removed.changed)
            self.assertFalse(path.exists())
            self.assertTrue(removed.backups[0].exists())

    def test_linux_install_uses_user_systemd_files_and_preserves_backups(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            service, timer = scheduler_paths(home, "Linux")
            service.parent.mkdir(parents=True)
            service.write_text("old service")

            result = install_scheduler(home=home, activate=False, system_name="Linux")

            self.assertTrue(result.changed)
            self.assertIn("ExecStart=sentinel run-due", service.read_text())
            self.assertIn("OnUnitActiveSec=60s", timer.read_text())
            self.assertEqual(result.backups[0].read_text(), "old service")

    def test_uninstall_refuses_unmanaged_file(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            path = scheduler_paths(home, "Darwin")[0]
            path.parent.mkdir(parents=True)
            path.write_bytes(plistlib.dumps({"Label": "someone.else"}))

            with self.assertRaisesRegex(ValueError, "unmanaged"):
                uninstall_scheduler(home=home, system_name="Darwin")

    def test_windows_task_is_created_without_replacing_an_unknown_task(self) -> None:
        responses = iter(
            [
                subprocess.CompletedProcess([], 1, "", "not found"),
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, "<Command>sentinel.exe</Command><Arguments>run-due</Arguments>", ""),
                subprocess.CompletedProcess([], 0, "", ""),
            ]
        )
        commands = []

        def runner(command, **_kwargs):
            commands.append(command)
            return next(responses)

        with TemporaryDirectory() as directory:
            home = Path(directory)
            installed = install_scheduler(
                home=home,
                executable="C:\\Tools\\sentinel.exe",
                system_name="Windows",
                runner=runner,
            )
            removed = uninstall_scheduler(home=home, system_name="Windows", runner=runner)

        self.assertTrue(installed.changed)
        self.assertTrue(installed.activated)
        self.assertTrue(removed.changed)
        self.assertIn("/Create", commands[1])
        self.assertIn("/Delete", commands[3])

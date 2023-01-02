# Copyright 2021 Erik Lönroth
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing
import pathlib
import sys
import unittest
from unittest.mock import patch

import ops.testing
from ops.testing import Harness

# Set testing environmental variable
ops.testing.SIMULATE_CAN_CONNECT = True

# Get paths
current_path = pathlib.Path.cwd()
src_path = current_path.parent.joinpath('src')
templates_path = current_path.parent.joinpath('templates')

print(f"Current path: {current_path.as_posix()}\n"
      f"src path: {src_path.as_posix()}, Valid: {src_path.is_dir()}\n"
      f"Templates path: {templates_path.as_posix()}, Valid: {templates_path.is_dir()}")

sys.path.append(src_path.as_posix())
try:
    from charm import GitlabRunnerCharm
    from gitlab_runner import register_docker
except ImportError:
    print("ERROR: Import of charm.GitlabRunnerCharm failed!")
    raise


class MockCharm:

    def __init__(self):
        self.config = dict()
        self.config['gitlab-server'] = 'https://gitlab.com'
        self.config['gitlab-registration-token'] = 'abcdEFGH'
        self.config['tag-list'] = ""
        self.config['concurrent'] = 1
        self.config['run-untagged'] = True
        self.config['locked'] = True
        self.config['executor'] = "docker"

        self.config[''] = ""
        self.config['check-interval'] = 3
        self.config['sentry-dsn'] = True
        self.config['locked'] = True
        self.config['concurrent'] = 1
        self.config['log-level'] = "error"
        self.config['log-format'] = "docker:latest"
        self.config['docker-image'] = "docker:latest"
        self.config['docker-tmpfs'] = "/scratch:rw,exec,size=1g"


class TestCharm(unittest.TestCase):

    def setUp(self):
        self.harness = Harness(GitlabRunnerCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('gitlab_runner.get_token')
    def test_01_config_changed_docker(self, mock_subprocess_popen, mock_subprocess_run, mock_get_token):
        # Mock return code from processes
        mock_subprocess_popen.return_value.returncode = 0
        mock_subprocess_run.return_value.returncode = 0
        mock_get_token.return_value = 'ABCDEFGH'

        harness = Harness(GitlabRunnerCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        # self.assertEqual(list(harness.charm._stored.executor), [])
        harness.update_config({"gitlab-registration-token": "abc",
                               "gitlab-server": "https://gitlab.com",
                               "executor": "docker"})
        print(f" Unit status after config changed:\n\t{harness.charm.unit.status}")
        self.assertEqual(harness.charm.config["executor"], "docker", msg='Executor not as configured')

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('gitlab_runner.get_token')
    def test_02_config_changed_lxd(self, mock_subprocess_popen, mock_subprocess_run, mock_get_token):
        # Mock return code from processes
        mock_subprocess_popen.return_value.returncode = 0
        mock_subprocess_run.return_value.returncode = 0
        mock_get_token.return_value = 'ABCDEFGH'

        harness = Harness(GitlabRunnerCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        # self.assertEqual(list(harness.charm._stored.executor), [])
        harness.update_config({"gitlab-registration-token": "abc",
                               "gitlab-server": "https://gitlab.com",
                               "executor": "lxd"})
        print(f" Unit status after config changed:\n\t{harness.charm.unit.status}")
        self.assertEqual(harness.charm.config["executor"], "lxd", msg='Executor not as configured')

    @patch('pathlib.Path.write_text')
    @patch('subprocess.Popen')
    def test_20_templates_runner_templates(self, mock_write_text, mock_subprocess_popen):
        # Mock return code from processes
        mock_subprocess_popen.return_value.returncode = 0

        test_charm = MockCharm()
        result = register_docker(test_charm)
        self.assertFalse(result, msg="Magically succeeded to render required templates")

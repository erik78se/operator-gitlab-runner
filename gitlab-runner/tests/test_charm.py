# Copyright 2021 Erik Lönroth
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing
import pathlib
import sys
import unittest
# from unittest.mock import Mock
# from ops.model import ActiveStatus
from ops.testing import Harness

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
except ImportError:
    print("ERROR: Import of charm.GitlabRunnerCharm failed!")
    raise


class TestCharm(unittest.TestCase):

    def setUp(self):
        self.harness = Harness(GitlabRunnerCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def unit_test_01_templates_runner_templates(self):
        pass

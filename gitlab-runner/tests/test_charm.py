# Copyright 2021 Erik Lönroth
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
# from unittest.mock import Mock

from charm import GitlabRunnerCharm
# from ops.model import ActiveStatus
from ops.testing import Harness


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(GitlabRunnerCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

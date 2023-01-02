#!/usr/bin/env python3
# Copyright 2021 Erik Lönroth
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import logging
import os
import subprocess
import shutil
import socket


from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main

from ops.model import (
    ActiveStatus,
    BlockedStatus,
    WaitingStatus
)

import gitlab_runner
import interface_prometheus

logger = logging.getLogger(__name__)


class GitlabRunnerCharm(CharmBase):
    """The charm"""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.prometheus_provider = interface_prometheus.PrometheusProvider(self, 'scrape', socket.getfqdn(), port=9252)

        # Charm persistent memory
        self._stored.set_default(executor=None,
                                 registered=False)

        # Events
        event_bindings = {
            self.on.install: self._on_install,
            self.on.config_changed: self._on_config_changed,
            self.on.start: self._on_start,
            self.on.stop: self._on_stop,
            self.on.update_status: self._on_update_status
        }

        # Actions
        action_bindings = {
            self.on.register_action: self._on_register_action,
            self.on.unregister_action: self._on_unregister_action,
            self.on.upgrade_action: self._on_upgrade_action
        }

        # Observe events and actions
        for event, handler in event_bindings.items():
            self.framework.observe(event, handler)

        for action, handler in action_bindings.items():
            self.framework.observe(action, handler)

    def _on_install(self, event):
        """
        INSTALL PROCESS DOCUMENTED HERE
        https://gitlab.com/gitlab-org/gitlab-runner/blob/master/docs/install/linux-repository.md
        """

        # Stage 1 - get upstream repo
        cmd = 'curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh | sudo bash'
        ps = subprocess.Popen(cmd, shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,
                              universal_newlines=True)
        output = ps.communicate()[0]
        logger.debug(output)

        # Stage 2 - install gitlab-runner
        install_cmd = 'sudo -E apt-get -y install gitlab-runner'
        gl_env = os.environ.copy()
        gl_env['GITLAB_RUNNER_DISABLE_SKEL'] = 'true'
        ps = subprocess.Popen(install_cmd, shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,
                              universal_newlines=True,
                              env=gl_env)
        output = ps.communicate()[0]
        logger.debug(output)

        # Stage 3 - install modified systemd unitfiles
        shutil.copy2('templates/etc/systemd/system/gitlab-runner.service',
                     '/etc/systemd/system/gitlab-runner.service')
        subprocess.run(['systemctl', 'daemon-reload'])
        subprocess.run(['systemctl', 'restart', 'gitlab-runner.service'])

        # Stage 4 - determine lxd/docker type executor
        e = self.config["executor"]
        if e == 'lxd':
            gitlab_runner.install_lxd_executor()
        elif e == 'docker':
            gitlab_runner.install_docker_executor()
        else:
            logger.error(f"Unsupported executor {e} configured, bailing out.")
            self.unit.status = BlockedStatus("Docker exec tmpfs config incorrect")

        v = gitlab_runner.get_gitlab_runner_version()
        self._stored.executor = e
        self.unit.set_workload_version(v)
        logger.debug("Completed install hook.")

    def _on_config_changed(self, _):
        if not gitlab_runner.check_mandatory_config_values(self):
            logger.error("Missing mandatory configs. Bailing.")
            self.unit.status = BlockedStatus("Missing mandatory config.")

        if not gitlab_runner.check_docker_tmpfs_config(self):
            logger.error("Configuration for Docker executor tmpfs config is incorrect. Bailing out!")
            self.unit.status = BlockedStatus("Docker exec tmpfs config incorrect")

        if not gitlab_runner.gitlab_runner_registered_already():
            logger.info("Registering")
            self.register()
        else:
            # The runner already registered
            logger.info("This runner is already registered. No action taken.")
            self.unit.status = ActiveStatus("Ready (Already registered.)")

        self._on_update_status(_)

    def _on_start(self, event):
        r = subprocess.run(['gitlab-runner', 'start'])
        if r.returncode == 0:
            logger.info("gitlab-runner started OK")
        else:
            logger.error("Failed to start gitlab-runner. Check logs.")
        self._on_update_status(event)

    def _on_update_status(self, event):
        token = gitlab_runner.get_token()
        if token:
            self.unit.status = ActiveStatus("Ready {executor}({token})".format(executor=self._stored.executor,
                                                                               token=token))
        else:
            self.unit.status = WaitingStatus("Not registered.")

    def _on_stop(self, event):
        gitlab_runner.unregister()
        self._stored.registered = False

    def _on_register_action(self, event):
        if not gitlab_runner.gitlab_runner_registered_already():
            if self.register():
                self._stored.registered = True
                event.set_results({"registered": True,
                                   "token": gitlab_runner.get_token()})
            else:
                event.fail("Failed to register.")
        else:
            event.fail("Already registered: {}".format(gitlab_runner.get_token()))

        self._on_update_status(event)

    def _on_unregister_action(self, event):
        gitlab_runner.unregister()
        self._stored.registered = False
        subprocess.run(['sudo', 'gitlab-runner', 'restart'])
        self.unit.status = WaitingStatus("Unregistered. Manual registration possible.")

    def register(self):
        # Pdb self.framework.breakpoint("register")
        logger.info(f"Register gitlab runner with executor: {self._stored.executor}")
        if self._stored.executor == 'docker':
            if gitlab_runner.register_docker(self, http_proxy=None, https_proxy=None):
                self._stored.registered = True
                logger.info("Ready (Registered)")
            else:
                logger.error("Failed in registration of Docker runner. Bailing out.")
                self._stored.registered = False

        elif self._stored.executor == 'lxd':
            if gitlab_runner.register_lxd(self, http_proxy=None, https_proxy=None):
                self._stored.registered = True
                logger.info("Ready (Registered)")
            else:
                logger.error("Failed in registration of lxd runner. Bailing out.")
                self._stored.registered = False
        else:
            logger.error("Unsupported runner class. Bailing out")
            self._stored.registered = False

        return self._stored.registered

    def _on_upgrade_action(self, event):

        logging.info("Executing upgrade of gitlab-runner with Docker executor")

        # Unregister current runner
        self._on_unregister_action(event)

        # Perform upgrade of gitlab-runner
        self.unit.status = WaitingStatus("Upgrading gitlab-runner")

        # Get and set environment variables
        gl_env = os.environ.copy()
        gl_env['GITLAB_RUNNER_DISABLE_SKEL'] = 'true'

        # Update gitlab-runner system
        cmd = 'sudo -E apt-get -y update'
        process = subprocess.Popen(cmd,
                                   shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,
                                   universal_newlines=True,
                                   env=gl_env)
        try:
            std_out, std_err = process.communicate(timeout=120)
            if std_out:
                logging.info(std_out)
            if std_err:
                logging.error(std_err)
        except subprocess.TimeoutExpired:
            process.kill()
            logging.error('Upgrade of gitlab-runner timed out and failed')
            return False

        # Upgrade all packages
        cmd = 'sudo -E apt-get -y upgrade'

        process = subprocess.Popen(cmd,
                                   shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,
                                   universal_newlines=True,
                                   env=gl_env)
        try:
            std_out, std_err = process.communicate(timeout=600)
            if std_out:
                logging.info(std_out)
            if std_err:
                logging.error(std_err)
        except subprocess.TimeoutExpired:
            process.kill()
            logging.error('Upgrade of gitlab-runner system timed out and failed')
            return False

        # Clean up system
        cmd = 'sudo -E apt-get -y autoremove'

        process = subprocess.Popen(cmd,
                                   shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,
                                   universal_newlines=True,
                                   env=gl_env)
        try:
            std_out, std_err = process.communicate(timeout=120)
            if std_out:
                logging.info(std_out)
            if std_err:
                logging.error(std_err)
        except subprocess.TimeoutExpired:
            process.kill()
            logging.error('Clean up of gitlab-runner system timed out and failed')
            return False

        # Register new runner
        self._on_register_action(event)


if __name__ == "__main__":
    main(GitlabRunnerCharm)

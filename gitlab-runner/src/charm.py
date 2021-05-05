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
from ops.model import ActiveStatus
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    ModelError,
    WaitingStatus
)

import gitlab_runner
from interface_prometheus import PrometheusProvider

logger = logging.getLogger(__name__)

class GitlabRunnerCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.prometheus_provider = PrometheusProvider(self, 'scrape', socket.getfqdn(), port=9252)
        # Hooks
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        # Actions
        self.framework.observe(self.on.fortune_action, self._on_fortune_action)

        # Charm persistent memory
        self._stored.set_default(executor=None,
                                 registered=False)


        # Events
        event_bindings = {
            self.on.install: self._on_install,
            self.on.config_changed: self._on_config_changed,
            self.on.start: self._on_start,
            self.on.update_status: self._on_update_status,
            self.on.scrape_relation_joined: self._on_scrape_relation_joined,
        }

        # Actions
        action_bindings = {
            self.on.list_runners_action: self._on_list_runners_action,
            self.on.register_action: self._on_register_action,
            self.on.unregister_action: self._on_unregister_action,
            self.on.unregister_all_runners_action: self._on_unregister_all_runners_action,
            self.on.verify_delete_action: self._on_verify_delete_action,
        }

        # Observe events and actions
        for event, handler in event_bindings.items():
            self.framework.observe(event, handler)

        for action, handler in action_bindings.items():
            self.framework.observe(action, handler)

    def _on_install(self,event):
        """
        INSTALL PROCESS DOCUMENTED HERE
        https://gitlab.com/gitlab-org/gitlab-runner/blob/master/docs/install/linux-repository.md
        """

        # Stage 1 - get upstream repo
        cmd = 'curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh | sudo bash'
        ps = subprocess.Popen(cmd,shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,
                              universal_newlines=True)
        output = ps.communicate()[0]
        logger.debug(output)

        # Stage 2 - install gitlab-runner
        install_cmd = 'sudo -E apt-get -y install gitlab-runner'
        gl_env = os.environ.copy()
        gl_env['GITLAB_RUNNER_DISABLE_SKEL'] = 'true'
        subprocess.Popen(install_cmd, env=gl_env)
        output = ps.communicate()[0]
        logger.debug(output)

        # Stage 3 - install systemd unitfiles
        shutil.copy2('templates/etc/systemd/system/gitlab-runner.service',
                     '/etc/systemd/system/gitlab-runner.service')
        subprocess.run(['systemctl', 'daemon-reload'])
        subprocess.run(['systemctl', 'status', 'gitlab-runner.service'])

        # Stage 4 - determine lxd/docker type executor
        e = self.config["executor"]
        if e == 'lxd':
            gitlab_runner.install_lxd_executor()
        elif e == 'docker':
            gitlab_runner.install_docker_executor()
        else:
            logger.error(f"Unsupported executor {e} configured, bailing out.")
            raise

        v = gitlab_runner.get_gitlab_runner_version()
        self._stored.set_default(executor=e)
        self.unit.set_workload_version(v)
        logger.debug("Completed install hook.")


    def _on_config_changed(self, _):
        if not gitlab_runner.check_mandatory_config_values(self):
            logger.error("Missing mandatory configs. Bailing.")
            self.unit.status = BlockedStatus("Missing mandatory config.")

        if not gitlab_runner.gitlab_runner_registered_already():
            self.register()
        else:
            # The runner already registered
            logger.info("This runner is already registered. No action taken.")
            self.unit.status = ActiveStatus("Ready (Already registered.)")

        self._on_update_status(_)

    def _on_start(self,event):
        r = subprocess.run(['gitlab-runner', 'start'])
        if r.returncode == 0:
            logger.info("gitlab-runner started OK")
        else:
            logger.error("Failed to start gitlab-runner. Check logs.")
        self._on_update_status(event)


    def _on_update_status(self,event):
        token = gitlab_runner.get_token()
        if token:
            self.unit.status = ActiveStatus("Ready {executor}({token})".format(executor=self._stored.executor,
                                                                                   token=token))
        else:
            self.unit.status = WaitingStatus("Not registered.")

    def _on_stop(self,event):
        hostname_fqdn = socket.getfqdn()
        subprocess.run(['gitlab-runner', 'unregister', '-n', hostname_fqdn, '--all-runners'])


    def _on_register_action(self, event):
        """
        curl --request POST "https://gitlab.example.com/api/v4/runners" \
        --form "token=${_token}" \
        --form "description=Deployed on $_hostname" \
        --form "tag_list=${_tag_list}" \
        Learn more about actions at https://juju.is/docs/sdk/actions
        """
        # fail = event.params["fail"]
        # if fail:
        #     event.fail(fail)
        # else:
        #     event.set_results({"fortune": "A bug in the code is worth two in the documentation."})
        if not gitlab_runner.gitlab_runner_registered_already():
            if self.register():
                event.set_results({"registered": True,
                                   "token": gitlab_runner.get_token() })
            else:
                event.fail("Failed to register.")
        else:
            event.fail("Already registered: {}".format(gitlab_runner.get_token()))


    def _on_unregister_action(self, event):
        self.unregister()
        subprocess.run(['sudo', 'gitlab-runner', 'restart'])
        self.unit.status = WaitingStatus("Unregistered. Manual registration possible.")


    def register(self):
        gs = self.config['gitlab-server']
        gt = self.config['gitlab-registration-token']
        tl = self.config['tag-list']
        c = self.config['concurrent']
        rut = (tl == [])
        if self._stored.executor == 'docker':
            di = self.config['docker-image']

            if gitlab_runner.register_docker(gs, gt, taglist=tl, concurrent=c, run_untagged=rut,
                                             dockerimage=di,
                                             http_proxy=None, https_proxy=None):
                self._stored.registered = True
                logger.info("Ready (Registered with " + gs + ")")
            else:
                logger.error("Failed in registration of runner. Bailing out.")
                raise
        elif self._stored.executor == 'lxd':
            if gitlab_runner.register_lxd(gs, gt, taglist=tl, concurrent=c, run_untagged=rut,
                                          http_proxy=None, https_proxy=None):
                self._stored.registered = True
                logger.info("Ready (Registered with " + gs + ")")
            else:
                logger.error("Failed in registration of runner. Bailing out.")
                raise

        return self._stored.registered


    def unregister(self):
        hostname_fqdn = socket.getfqdn()
        subprocess.run(['gitlab-runner', 'unregister', '-n', hostname_fqdn, '--all-runners'])

if __name__ == "__main__":
    main(GitlabRunnerCharm)

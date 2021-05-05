#!/usr/bin/env python3
# Copyright 2021 Erik Lönroth
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk
import logging
import os, stat, re
import glob
import shutil
import socket
import subprocess
import toml



def install_lxd_executor():
    subprocess.run(['useradd', '-g', 'lxd', 'gitlab-runner'])
    subprocess.run(['mkdir', '-p', '/opt/lxd-executor'])
    for file in glob.glob('templates/lxd-executor/*.sh'):
        shutil.copy2(file,'/opt/lxd-executor/')
        os.chmod("/opt/lxd-executor/"+file, stat.S_IEXEC)
    subprocess.run(['lxd', 'init', '--auto'])


def install_docker_executor():
    subprocess.run(['apt', 'install', '-y', 'docker.io'])
    subprocess.run(['systemctl', 'start', 'docker.service'])


def get_gitlab_runner_version():
    cmd = "gitlab-runner --version"
    r = subprocess.run(cmd.split(), capture_output=True, universal_newlines=True)
    return re.search('Version:(.*)', r.stdout).group(1).lstrip()


def check_mandatory_config_values(charm):
    nonempty = []
    nonempty.append(charm.config['gitlab-registration-token'])
    nonempty.append(charm.config['gitlab-server'])
    nonempty.append(charm.config['executor'])
    return all(nonempty)


def gitlab_runner_registered_already():
    hostname_fqdn = socket.getfqdn()
    cp = subprocess.run(("gitlab-runner verify -n " + hostname_fqdn).split())
    return cp.returncode == 0


def register_docker(gitlabserver,gitlabregistrationtoken,taglist=[],concurrent=None,run_untagged=False,dockerimage=None,
                     https_proxy=None,http_proxy=None):

    hostname_fqdn = socket.getfqdn()

    proxyenv = ""
    cmd = f"gitlab-runner register --non-interactive \
    --config /etc/gitlab-runner/config.toml \
    --template-config /tmp/runner-template-config.toml \
    --name {hostname_fqdn} \
    --url {gitlabserver} \
    --registration-token {gitlabregistrationtoken} \
    --tag-list {taglist} \
    --request-concurrency {concurrent} \
    --run-untagged={run_untagged} \
    --executor docker \
    --docker-image {dockerimage} \
    {proxyenv}"

    cp = subprocess.run(cmd.split())
    logging.debug(cp.stdout)
    return cp.returncode == 0


def register_lxd(gitlabserver,gitlabregistrationtoken,taglist=[],concurrent=None,run_untagged=False,
                     https_proxy=None,http_proxy=None):
    hostname_fqdn = socket.getfqdn()

    cmd = f"gitlab-runner register --non-interactive \
    --config /etc/gitlab-runner/config.toml \
    --template-config /tmp/runner-template-config.toml \
    --name {hostname_fqdn} \
    --url {gitlabserver} \
    --registration-token {gitlabregistrationtoken} \
    --tag-list {taglist} \
    --request-concurrency {concurrent} \
    --run-untagged={run_untagged} \
    --executor custom \
    --builds-dir /builds \
    --cache-dir /cache \
    --custom-run-exec /opt/lxd-executor/run.sh \
    --custom-prepare-exec /opt/lxd-executor/prepare.sh \
    --custom-cleanup-exec /opt/lxd-executor/cleanup.sh"
    cp = subprocess.run(cmd.split())
    logging.debug(cp.stdout)
    return cp.returncode == 0

def get_token():
    """
    Returns: The 8 first chars of the token
    """
    with open('/etc/gitlab-runner/config.toml') as f:
        try:
            data = toml.load(f)
            return data['runners'][0]['token'][0:8]
        except(KeyError) as e:
            return None

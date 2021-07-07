#!/usr/bin/env python3
# Copyright 2021 Erik Lönroth
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk
import logging
import stat
import re
import glob
import shutil
import socket
import subprocess
import toml
from pathlib import Path
import jinja2


def install_lxd_executor():
    subprocess.run(['useradd', '-g', 'lxd', 'gitlab-runner'])
    subprocess.run(['mkdir', '-p', '/opt/lxd-executor'])
    for file in glob.glob('templates/lxd-executor/*.sh'):
        f = Path(file)
        installed_file = Path(shutil.copy2(f, '/opt/lxd-executor/'))
        installed_file.chmod(stat.S_IEXEC)
    subprocess.run(['lxd', 'init', '--auto'])


def install_docker_executor():
    subprocess.run(['apt', 'install', '-y', 'docker.io'])
    subprocess.run(['systemctl', 'start', 'docker.service'])


def get_gitlab_runner_version():
    cmd = "gitlab-runner --version"
    r = subprocess.run(cmd.split(),
                       stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT,
                       universal_newlines=True)
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


def register_docker(charm, https_proxy=None, http_proxy=None):

    # Render #1 - global config
    templates_path = Path('templates/etc/gitlab-runner/')
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path)
    ).get_template('config.toml')
    target = Path('/etc/gitlab-runner/config.toml')
    ctx = {'concurrent': charm.config['concurrent'],
           'checkinterval': charm.config['check-interval'],
           'sentrydsn': charm.config['sentry-dsn'],
           'loglevel': charm.config['log-level'],
           'logformat': charm.config['log-format']}
    target.write_text(template.render(ctx))

    # Render #2 - runner template.
    # render-docker-runner-template
    templates_path = Path('templates/runner-templates/')
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path)
    ).get_template('docker-1.template')
    target = Path('/tmp/runner-template-config.toml')
    ctx = {'dockerimage': charm.config['docker-image']}
    target.write_text(template.render(ctx))

    hostname_fqdn = socket.getfqdn()
    gitlabserver = charm.config['gitlab-server']
    gitlabregistrationtoken = charm.config['gitlab-registration-token']
    taglist = charm.config['tag-list']
    concurrent = charm.config['concurrent']
    dockerimage = charm.config['docker-image']
    run_untagged = charm.config['run-untagged']
    locked = charm.config['locked']
    proxyenv = ""

    cmd = f"gitlab-runner register \
    --non-interactive \
    --config /etc/gitlab-runner/config.toml \
    --template-config /tmp/runner-template-config.toml \
    --name {hostname_fqdn} \
    --url {gitlabserver} \
    --registration-token {gitlabregistrationtoken} \
    --tag-list {taglist} \
    --request-concurrency {concurrent} \
    --run-untagged={run_untagged} \
    --locked={locked} \
    --executor docker \
    --docker-image {dockerimage} \
    {proxyenv}"

    cp = subprocess.run(cmd.split())
    logging.debug(cp.stdout)
    return cp.returncode == 0


def register_lxd(charm, https_proxy=None, http_proxy=None):
    hostname_fqdn = socket.getfqdn()
    gitlabserver = charm.config['gitlab-server']
    gitlabregistrationtoken = charm.config['gitlab-registration-token']
    taglist = charm.config['tag-list']
    concurrent = charm.config['concurrent']
    run_untagged = charm.config['run-untagged']
    locked = charm.config['locked']

    # Render #1 - global config
    templates_path = Path('templates/etc/gitlab-runner/')
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path)
    ).get_template('config.toml')
    target = Path('/etc/gitlab-runner/config.toml')
    ctx = {'concurrent': charm.config['concurrent'],
           'checkinterval': charm.config['check-interval'],
           'sentrydsn': charm.config['sentry-dsn'],
           'loglevel': charm.config['log-level'],
           'logformat': charm.config['log-format']}
    target.write_text(template.render(ctx))

    # Build register command
    cmd = f"gitlab-runner register \
    --non-interactive \
    --config /etc/gitlab-runner/config.toml \
    --name {hostname_fqdn} \
    --url {gitlabserver} \
    --registration-token {gitlabregistrationtoken} \
    --tag-list {taglist} \
    --request-concurrency {concurrent} \
    --run-untagged={run_untagged} \
    --locked={locked} \
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
            return str(e)


def unregister():
    hostname_fqdn = socket.getfqdn()
    cmd = f"gitlab-runner unregister -n {hostname_fqdn} --all-runners"
    cp = subprocess.run(cmd.split())
    logging.debug(cp.stdout)
    return cp.returncode == 0

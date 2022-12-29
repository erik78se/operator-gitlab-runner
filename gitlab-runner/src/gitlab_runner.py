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


def check_mandatory_config_values(charm) -> bool:
    nonempty = list()
    nonempty.append(charm.config['gitlab-registration-token'])
    nonempty.append(charm.config['gitlab-server'])
    nonempty.append(charm.config['executor'])
    return all(nonempty)


def check_docker_tmpfs_config(charm) -> bool:
    if charm.config['docker-tmpfs'] != '':
        try:
            a, b = charm.config['docker-tmpfs'].split(':')
        except ValueError:
            return False
    return True


def gitlab_runner_registered_already() -> bool:
    hostname_fqdn = socket.getfqdn()
    cp = subprocess.run(("gitlab-runner verify -n " + hostname_fqdn).split())
    return cp.returncode == 0


def register_docker(charm, https_proxy=None, http_proxy=None) -> bool:

    try:
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
    except jinja2.exceptions.TemplateSyntaxError as e:
        logging.error('ERROR: Template config.toml could not be rendered due to syntax error\n'
                      f'\tProblem: {e}')
        return False
    except jinja2.TemplateError as e:
        logging.error('ERROR: Template config.toml could not be rendered\n'
                      f'\tProblem: {e}')
        return False

    try:
        # Render #2 - runner template.
        # render-docker-runner-template
        templates_path = Path('templates/runner-templates/')
        template = jinja2.Environment(
            loader=jinja2.FileSystemLoader(templates_path,),
            undefined=jinja2.StrictUndefined
        ).get_template('docker-1.template')
        target = Path('/tmp/runner-template-config.toml')
        ctx = {'docker_image': charm.config['docker-image']}
        # If tmpfs was defined for Docker executor, render required config.
        if charm.config['docker-tmpfs'] != '':
            docker_tmpfs_path, docker_tmpfs_config = charm.config['docker-tmpfs'].split(':')
            ctx['docker_tmpfs_path'] = docker_tmpfs_path
            ctx['docker_tmpfs_config'] = docker_tmpfs_config
        target.write_text(template.render(ctx))
    except jinja2.exceptions.TemplateNotFound:
        logging.error("ERROR: Template docker-1.template could not be found.")
        return False
    except jinja2.exceptions.TemplateSyntaxError as e:
        logging.error('ERROR: Template docker-1.template could not be rendered due to syntax error\n'
                      f'\tProblem: {e}')
        return False
    except jinja2.exceptions.UndefinedError as e:
        logging.error('ERROR: Template docker-1.template could not be rendered due to syntax error\n'
                      f'\tProblem: {e}')
        return False
    except jinja2.TemplateError as e:
        logging.error('ERROR: Template docker-1.template could not be rendered\n'
                      f'\tProblem: {e}')
        return False

    hostname_fqdn = socket.getfqdn()
    gitlab_server = charm.config['gitlab-server']
    gitlab_registration_token = charm.config['gitlab-registration-token']
    tag_list = charm.config['tag-list']
    concurrent = charm.config['concurrent']
    # Defined in docker-1.template
    # docker_image = charm.config['docker-image']
    run_untagged = charm.config['run-untagged']
    locked = charm.config['locked']
    proxyenv = ""

    cmd = ["gitlab-runner", "register",
           "--non-interactive",
           "--config", "/etc/gitlab-runner/config.toml",
           "--template-config", "/tmp/runner-template-config.toml",
           "--name", f"{hostname_fqdn}",
           "--url", f"{gitlab_server}",
           "--registration-token", f"{gitlab_registration_token}",
           "--request-concurrency", f"{concurrent}",
           f"--run-untagged={run_untagged}",
           f"--locked={locked}",
           "--executor", "docker",
           f"{proxyenv}"]

    if not run_untagged and tag_list != "":
        cmd.extend(["--tag-list", "{tag-list}"])
    if run_untagged and tag_list != "":
        logging.warning('Conflicting configuration, run-untagged=True and tag_list are mutually exclusive. \
        Skipping tag-list.')

    logging.info("Executing registration call for gitlab-runner with Docker executor")
    process = subprocess.Popen(cmd)
    try:
        std_out, std_err = process.communicate(timeout=30)
        if std_out:
            logging.info(std_out)
        if std_err:
            logging.error(std_err)
    except subprocess.TimeoutExpired:
        process.kill()
        logging.error('Registration of gitlab-runner timed out and failed')
        return False

    logging.info(f'Registration of Docker executor finished with exit code: {process.returncode}')
    return process.returncode == 0


def register_lxd(charm, https_proxy=None, http_proxy=None) -> bool:
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


def get_token() -> str:
    """
    Returns: The 8 first chars of the token
    """
    with open('/etc/gitlab-runner/config.toml') as f:
        try:
            data = toml.load(f)
            return data['runners'][0]['token'][0:8]
        except KeyError as e:
            return str(e)


def unregister() -> bool:
    hostname_fqdn = socket.getfqdn()
    cmd = f"gitlab-runner unregister -n {hostname_fqdn} --all-runners"
    cp = subprocess.run(cmd.split())
    logging.debug(cp.stdout)
    return cp.returncode == 0

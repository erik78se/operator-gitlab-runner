#!/usr/bin/env bash

# /opt/lxd-executor/prepare.sh

currentDir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
source ${currentDir}/base.sh # Get variables from base.

set -eo pipefail

# trap any error, and mark it as a system failure.
trap "exit $SYSTEM_FAILURE_EXIT_CODE" ERR

# default to Ubuntu 18.04 if none has been set with the 'image' keyword in the .gitlab-ci.yml
CUSTOM_ENV_CI_JOB_IMAGE="${CUSTOM_ENV_CI_JOB_IMAGE:-ubuntu:18.04}"

prepare_network () {

    # prevent name collisions when using nested LXD on .lxd
    lxc network set lxdbr0 dns.domain juju-gitlab-runner 

}

start_container () {
    if lxc info "$CONTAINER_ID" >/dev/null 2>/dev/null ; then
        echo 'Found old container, deleting'
        lxc delete -f "$CONTAINER_ID"
    fi

    # make sure profile is configured correctly
    if lxc profile show gitlab > /dev/null 2> /dev/null ; then
        echo 'Found existing profile, skipping creation'
    else
	lxc profile create gitlab
    fi
    lxc profile set gitlab security.nesting true
    lxc profile set gitlab security.privileged true
    printf "lxc.apparmor.profile=unconfined\nlxc.mount.auto=sys:rw\n" | lxc profile set gitlab raw.lxc -

    lxc launch "$CUSTOM_ENV_CI_JOB_IMAGE" "$CONTAINER_ID" -p gitlab -p default

    # Wait for container to start, we are using systemd to check this,
    # for the sake of brevity.
    for i in $(seq 1 10); do
        if lxc exec "$CONTAINER_ID" -- sh -c "systemctl isolate multi-user.target" >/dev/null 2>/dev/null; then
            break
        fi

        if [ "$i" == "10" ]; then
            echo 'Waited for 10 seconds to start container, exiting..'
            # Inform GitLab Runner that this is a system failure, so it
            # should be retried.
            exit "$SYSTEM_FAILURE_EXIT_CODE"
        fi

        sleep 1s
    done
}

install_dependencies () {
    # Install Git LFS, git comes pre installed with ubuntu image.
    lxc exec "$CONTAINER_ID" -- sh -c "curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.deb.sh | sudo bash"
    lxc exec "$CONTAINER_ID" -- sh -c "apt install -y git-lfs"

    # Install gitlab-runner binary since we need for cache/artifacts.
    lxc exec "$CONTAINER_ID" -- sh -c "curl -L --output /usr/local/bin/gitlab-runner https://gitlab-runner-downloads.s3.amazonaws.com/latest/binaries/gitlab-runner-linux-amd64"
    lxc exec "$CONTAINER_ID" -- sh -c "chmod +x /usr/local/bin/gitlab-runner"
}

echo "Running in $CONTAINER_ID"

prepare_network

start_container

install_dependencies

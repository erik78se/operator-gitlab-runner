# Overview

A gitlab-runner charm.

The charm works like this:

* Installs gitlab-runner upstream repos as described here:
https://gitlab.com/gitlab-org/gitlab-runner/blob/main/docs/install/linux-repository.md

* Configures and registers a single docker or lxd runner using the configured gitlab-registration-token.

* Exposes prometheus metrics on port: 9252

The runner registers with its hostname (fqdn) in gitlab (default with gitlab-runner) and any supplied tags. 
A default "juju" tag is added unless changed.

The runner removes itself and unregisters as part of a unit removal with 'juju remove unit'.

Some actions are available to help register/unregister plus some more.

# Mandatory configuration details.

The following configurations are mandatory:

* **gitlab-registration-token** : Get this from your gitlab repo under "Settings -> CI/CD".
* **gitlab-server** : The URL address to your gitlab server used to perform the gitlab-runner registration.

## LXD runners
Default lxd image will be set to ubuntu:18.04 if none has been set with the 'image' keyword in the .gitlab-ci.yml

This can be changed also with the CUSTOM_ENV_CI_JOB_IMAGE variable in your gitlab project.

## Group runners

By setting the locked=false config, the runner registers as a non-locked runner. Requires the runner to be re-registered.

    juju config gitlab-runner locked=false
    juju run gitlab-runner/0 unregister
    juju run gitlab-runner/0 register

# Example deploy & scaling
This example show a basic deploy scaling to N runners.

Create a file with your configuration: runner-config.yaml:

```yaml
gitlab-runner:
  gitlab-server: "https://gitlab.example.com"
  gitlab-registration-token: tXwQuDAVmzxzzTtw2-ZL
  tag-list: "juju,docker,master"
  run-untagged: true
```

Then deploy with your config and some instance constraints.

```bash
  juju deploy --constraints="mem=4G cores=2" ./builds/gitlab-runner --config runner-config.yaml
```
Scale up your deployment with 'juju add-unit' and you will get an identical new instance. serving your pipeline:
```bash
  juju add-unit gitlab-runner
```

Scale down with 'juju remove-unit' (will also unregister the instance in gitlab)
```bash
  juju remove-unit gitlab-runner/0
```

# Example deploy, multiple projects, different sizes

Create two files with your separate configurations.

runner-config-one.yaml
```yaml
gitlab-runner-one:
  gitlab-server: "https://gitlab.example.com"
  gitlab-registration-token: rXwQugergrzxzz32Fw3-44
  tag-list: "juju,docker,master"
  run-untagged: true
```

runner-config-two.yaml
```yaml
gitlab-runner-two:
  gitlab-server: "https://gitlab.example.com"
  gitlab-registration-token: tXwQuDAVmzxzzTtw2-ZL
  tag-list: "juju,docker,daily"
  run-untagged: true
```

Deploy the same charm, using two differnt configs and different constraints.

```bash
  juju deploy --constraints="mem=4G cores=2" ./builds/gitlab-runner gitlab-runner-one --config runner-config-one.yaml
  juju deploy --constraints="mem=2G cores=1" ./builds/gitlab-runner gitlab-runner-two --config runner-config-two.yaml
```

# Example deploy, relate to prometheus for monitoring

With any of the other examples, add in a prometheus instance:

```bash
  juju deploy prometheus2 --constraints="mem=4G cores=2"
  juju relate prometheus2 gitlab-runner
  juju expose prometheus2
```

When ready, the prometheus instance will be available on http://prometheus-instance:9090/

# About runner tag-list
Tags are added when a runner is registered (deployed) and can only be changed after through the gitlab server GUI or APIs unavailable to gitlab-runners.

Consequently, charm config changes in the charm will not have an impact inside of gitlab. Changes to the tag-list takes effect only for new units.

# Contact Information
Erik Lönroth: erik.lonroth@gmail.com

https://eriklonroth.com

# Upstream charm repo
Repo at https://github.com/erik78se/operator-gitlab-runner

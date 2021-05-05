#!/usr/bin/python3
"""prometheus scrape interface (provides side)."""

from ops.framework import Object


class PrometheusProvider(Object):
    """Prometheus  provider interface."""

    def __init__(self, charm, relation_name, hostname="", port=9100, metrics_path='/metrics'):
        """Set the initial data.
        """
        super().__init__(charm, relation_name)
        self._relation_name = relation_name
        self._hostname = hostname  # FQDN of host passed on in relations
        self._port = port
        self._metrics_path = metrics_path
        self.framework.observe(
            charm.on[relation_name].relation_joined, self._on_relation_joined
        )

    def _on_relation_joined(self, event):
        """
        We use this event for passing on hostname and port and metrics_path.
        :param event:
        :return:
        """
        event.relation.data[self.model.unit]['hostname'] = self._hostname
        event.relation.data[self.model.unit]['port'] = str(self._port)
        event.relation.data[self.model.unit]['metrics_path'] = str(self._metrics_path)
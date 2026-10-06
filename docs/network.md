# Network notes

The lab runs on a **single Docker bridge network** `atb` (subnet `172.31.0.0/16`,
change it in `docker-compose.yml` if it collides). Containers reach each other by
service name; the scenario's production FQDNs and IPs are attached as **network
aliases** so the write-up's hostnames resolve (e.g. `www.atbmarket.com`,
`sp-web-p01`, `zb-app-p01`, `erpdb`, `DC-MAIN-01.atbmarket.com`).

Real segmentation (multiple VLANs / the `172.16.x` and `10.0.x` ranges in the
report) is **not** reproduced — it isn't needed to exercise the attack chain, and
one flat network keeps the lab simple and portable. The production IPs in
[`asset-inventory.md`](./asset-inventory.md) are illustrative; use the DNS
aliases / host ports instead.

## Host-port map

See the port list in [`../README.md`](../README.md#host-ports). From the host you
reach each service at `localhost:<port>`; from inside a container, by service name
or alias on port 80 (web) / native port (DB, ZBXD, ssh).

## Pivot path (steps 6–7)

`supplier` → `grafana` → `zabbix` (root) → `squid` proxy → `jenkins` (ZBXD) →
`/mnt/BACKUP` (shared volume standing in for the `bkp-atman` CIFS share) →
`id_rsa_root` → `bastion` / `gitlab`. All of it rides the one `atb` network; the
squid container exists to represent the "trusted /28" hop from the report.

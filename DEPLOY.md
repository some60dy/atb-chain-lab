# ATB Market Lab — Deployment Guide

Self-contained Docker lab that reproduces a 10-step attack chain + Splunk SIEM.
Everything builds from source in this folder — no images to pull except public
base images (python, mysql, postgres, splunk, squid).

> ⚠️ **Lab only / isolated use.** Every credential and vulnerability here is
> fictional and deliberately insecure. Run on an isolated host/VM. Do **not**
> expose any port to an untrusted network.

## 1. Requirements

- Linux (or WSL2 / macOS) with **Docker Engine ≥ 24** and the **compose v2** plugin
  - check: `docker --version && docker compose version`
- ~**8 GB** free RAM (Splunk alone wants ~2 GB) and ~**6 GB** free disk
- Ports free on the host (see list in §5). Internet access on first run to pull
  the public base images.
- `make`, `bash`, `curl`, `python3` (for the attack scripts), `ssh`, `tar`.

## 2. Deploy (3 commands)

```bash
tar -xzf atb-market-lab.tar.gz        # unpack
cd atb-lab
make up                               # bootstrap keys -> build -> start everything
```

`make up` runs `bootstrap.sh` (generates the lab's throwaway SSH key + the
"leaked" backup), builds the shared base image, builds every service, and starts
all 19 containers. **First run takes ~5–10 min** (pulls Splunk ~2.5 GB + builds).

Wait ~60–90 s after it returns for MySQL/Postgres to seed and Splunk to finish
starting, then:

```bash
make ps            # all services should be "running"
make chain         # drive the whole attack chain; prints each step's result
```

Open **Splunk** → http://localhost:8000  (`admin` / `changeme`)
Search: `index=atb | sort 0 _time | table _time host service event src_ip msg`

## 3. Daily use

```bash
make up        # start            make down     # stop (keep data)
make chain     # run the attack   make logs     # follow container logs
make ps        # status           make reset    # stop + wipe volumes & logs (clean slate)
```

Per-step testing commands are in `docs/attack-chain.md`; detections in
`splunk/detections.md`; the full asset/credential map in `docs/asset-inventory.md`.

## 4. If a port is already taken

Edit the `ports:` mapping of the offending service in `docker-compose.yml`
(left side = host port) and `make up` again. Scripts in `attack/` take the base
URL/port as an argument if you remap.

## 5. If the Docker subnet collides

Symptom on `make up`: *"Pool overlaps with other one on this address space"*.
Edit `docker-compose.yml` → `networks.atb.ipam.config.subnet` (default
`172.31.0.0/16`) to a free range, e.g. `172.28.0.0/16`, then `make up`.

Host ports: shop 8080 · mobapp 8081 · education 8082 · supplier 8083 ·
zabbix 8084 · harbor 8085 · ad-ldap 8386 · grafana 3000 · exchange 8444 ·
jenkins/ZBXD 10050 · oracle 1581/1521/1251 · squid 3128 · bastion ssh 2210 ·
gitlab ssh 2222 · mysql 3306/3307/3308 · postgres 5432 · **splunk 8000**.

## 6. Teardown

```bash
make reset                 # stop + remove volumes + clear logs
make clean                 # also remove the atb-base image
docker compose down -v     # (equivalent hard stop)
```

## 7. What's NOT shipped

The archive excludes `logs/`, `keys/`, `backup-seed/`, Splunk's data volume and
`__pycache__`. The SSH key and backup are **regenerated locally** by
`bootstrap.sh` on first `make up`, so no secrets travel in the archive and the
lab still works out of the box.

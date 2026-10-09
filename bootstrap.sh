#!/usr/bin/env bash
# One-time setup: generate the lab's throwaway SSH key + the "leaked" backup
# tarball, and create the logs dir. Safe to re-run (idempotent).
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p keys backup-seed logs
chmod 777 logs 2>/dev/null || true

if [ ! -f keys/id_rsa_root ]; then
  echo "[bootstrap] generating keys/id_rsa_root ..."
  ssh-keygen -t rsa -b 2048 -N '' -C 'id_rsa_root' -f keys/id_rsa_root >/dev/null
fi

if [ ! -f backup-seed/root.tar.gz ]; then
  echo "[bootstrap] building backup-seed/root.tar.gz (the key the lab leaks) ..."
  tmp=$(mktemp -d)
  mkdir -p "$tmp/root/.ssh"
  cp keys/id_rsa_root "$tmp/root/.ssh/id_rsa_root"
  chmod 600 "$tmp/root/.ssh/id_rsa_root"
  cat > "$tmp/root/.ssh/config" <<'CFG'
Host bastion
    HostName bastion-main-p01
    User root
    IdentityFile ~/.ssh/id_rsa_root

Host gitlab
    HostName gitlab-p01
    User root
    IdentityFile ~/.ssh/id_rsa_root
    ProxyJump bastion
CFG
  printf '%s\n' 'ssh bastion' 'ssh gitlab' 'scp -r /etc/zabbix bastion:/tmp/' > "$tmp/root/.bash_history"
  tar -czf backup-seed/root.tar.gz -C "$tmp" root/.ssh/id_rsa_root root/.ssh/config root/.bash_history
  rm -rf "$tmp"
fi

echo "[bootstrap] ok"

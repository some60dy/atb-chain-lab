FROM debian:12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-server ca-certificates curl default-mysql-client postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd /root/.ssh /var/log/atb
# trust the root key that the attacker recovers from the CIFS backup
COPY keys/id_rsa_root.pub /root/.ssh/authorized_keys
COPY services/bastion/sshrc /etc/ssh/sshrc
COPY services/bastion/fs/bash_history /root/.bash_history
RUN chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys \
    && chmod 755 /etc/ssh/sshrc \
    && sed -i 's/#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config \
    && sed -i 's/#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
EXPOSE 22
CMD ["/usr/sbin/sshd","-D","-e"]

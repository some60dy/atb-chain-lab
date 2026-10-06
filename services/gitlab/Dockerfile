FROM debian:12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-server ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd /root/.ssh /var/log/atb /var/opt/gitlab/git-data/repositories
COPY keys/id_rsa_root.pub /root/.ssh/authorized_keys
COPY services/gitlab/sshrc /etc/ssh/sshrc
# materialise 524 bare-repo directories (git-data) as in the report
RUN for i in $(seq 1 524); do \
      d=$(printf '/var/opt/gitlab/git-data/repositories/group%03d/project%03d.git' $((i%40)) $i); \
      mkdir -p "$d/refs" "$d/objects"; \
      echo "ref: refs/heads/main" > "$d/HEAD"; \
    done \
    && chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys \
    && chmod 755 /etc/ssh/sshrc \
    && sed -i 's/#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config \
    && sed -i 's/#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
EXPOSE 22
CMD ["/usr/sbin/sshd","-D","-e"]

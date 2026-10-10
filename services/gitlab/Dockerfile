FROM debian:12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-server ca-certificates busybox \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd /root/.ssh /var/log/atb /var/opt/gitlab/git-data/repositories /var/www
COPY keys/id_rsa_root.pub /root/.ssh/authorized_keys
COPY services/gitlab/sshrc /etc/ssh/sshrc
COPY services/gitlab/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY services/gitlab/www/head.html services/gitlab/www/foot.html /tmp/www/
# materialise 524 bare-repo directories (git-data) as in the report
RUN for i in $(seq 1 524); do \
      d=$(printf '/var/opt/gitlab/git-data/repositories/group%03d/project%03d.git' $((i%40)) $i); \
      mkdir -p "$d/refs" "$d/objects"; \
      echo "ref: refs/heads/main" > "$d/HEAD"; \
    done \
    # build the static mock-GitLab projects page (head + 524 rows + foot)
    && { cat /tmp/www/head.html; \
         for i in $(seq 1 524); do \
           n=$(printf 'project%03d' $i); g=$(printf 'group%03d' $((i%40))); \
           printf '<li><span class="pic">%s</span><span class="name"><span class="ns">atbmarket/%s/</span>%s</span><span class="meta"><span class="vis">Private</span><span>main</span></span></li>\n' \
             "$(printf %s "$n" | cut -c9-10)" "$g" "$n"; \
         done; \
         cat /tmp/www/foot.html; } > /var/www/index.html \
    && rm -rf /tmp/www \
    && chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys \
    && chmod 755 /etc/ssh/sshrc /usr/local/bin/entrypoint.sh \
    && sed -i 's/#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config \
    && sed -i 's/#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config \
    && echo 'AllowUsers root@172.31.0.10' >> /etc/ssh/sshd_config
EXPOSE 22 80
CMD ["/usr/local/bin/entrypoint.sh"]

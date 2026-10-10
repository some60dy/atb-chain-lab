#!/bin/sh
# mock GitLab web (static, non-clickable) + the real sshd
busybox httpd -p 80 -h /var/www
exec /usr/sbin/sshd -D -e

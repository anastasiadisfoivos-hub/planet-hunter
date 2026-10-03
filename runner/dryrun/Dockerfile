# A stand-in for a fresh Oracle Cloud Ubuntu 24.04 arm64 instance: systemd as PID 1, OpenSSH, an `ubuntu` user
# with passwordless sudo and key-only login. deploy.sh talks to it exactly as it would to the real server.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends systemd systemd-sysv dbus openssh-server \
      sudo ca-certificates curl iproute2 iptables kmod && rm -rf /var/lib/apt/lists/* \
 && (id ubuntu >/dev/null 2>&1 || useradd -m -s /bin/bash ubuntu) \
 && echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-ubuntu && chmod 440 /etc/sudoers.d/90-ubuntu \
 && mkdir -p /home/ubuntu/.ssh && chmod 700 /home/ubuntu/.ssh \
 && systemctl enable ssh \
 && rm -f /etc/systemd/system/multi-user.target.wants/getty* /lib/systemd/system/getty.target.wants/* || true
COPY authorized_keys /home/ubuntu/.ssh/authorized_keys
RUN chown -R ubuntu:ubuntu /home/ubuntu/.ssh && chmod 600 /home/ubuntu/.ssh/authorized_keys
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]

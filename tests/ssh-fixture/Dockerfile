FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssh-server && rm -rf /var/lib/apt/lists/* && mkdir -p /run/sshd && useradd -m -s /bin/bash agent && echo 'agent:fixture-only-disabled-password-auth' | chpasswd
COPY agent_pool /opt/agent-pool/agent_pool
COPY pool /usr/local/bin/agent-pool
COPY fake_codex /usr/local/bin/codex
COPY fake_claude /usr/local/bin/claude
COPY authorized_keys /home/agent/.ssh/authorized_keys
RUN chmod 755 /usr/local/bin/agent-pool /usr/local/bin/codex /usr/local/bin/claude && mkdir -p /home/agent/work && chown -R agent:agent /home/agent && chmod 700 /home/agent/.ssh && chmod 600 /home/agent/.ssh/authorized_keys && printf '\nPasswordAuthentication no\nPermitRootLogin no\nAllowUsers agent\n' >> /etc/ssh/sshd_config
ENV PYTHONPATH=/opt/agent-pool
EXPOSE 22
CMD ["/usr/sbin/sshd", "-D", "-e"]

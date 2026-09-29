#!/bin/sh
# Install or reconfigure the New Relic infrastructure agent on the VM: host, process and Docker container
# metrics plus the system, auth and backup logs. Safe to run again; it rewrites the config and restarts the agent.
#   sudo /opt/dcss/newrelic.sh <license-key>
# The key is an INGEST - LICENSE key from one.newrelic.com > Administration > API keys (account 1047501).
# The New Relic apt repository is outside unattended-upgrades' origins, so upgrade the agent by hand:
# `sudo apt-get update && sudo apt-get install --only-upgrade newrelic-infra`.
set -eu
KEY="${1:?usage: newrelic.sh <license-key>}"
CODENAME=$(sed -n 's/^VERSION_CODENAME=//p' /etc/os-release)

install -d -m 755 /etc/apt/keyrings
curl -fsSL https://download.newrelic.com/infrastructure_agent/gpg/newrelic-infra.gpg |
  gpg --dearmor --yes -o /etc/apt/keyrings/newrelic-infra.gpg
echo "deb [signed-by=/etc/apt/keyrings/newrelic-infra.gpg] https://download.newrelic.com/infrastructure_agent/linux/apt/ $CODENAME main" \
  >/etc/apt/sources.list.d/newrelic-infra.list

# written before the package is installed so the agent has a key the first time it starts
umask 077
cat >/etc/newrelic-infra.yml <<CONF
license_key: $KEY
enable_process_metrics: true
custom_attributes:
  service: crawl.han.life
CONF
umask 022

# Container logs are not here: the compose file uses Docker's `local` log driver, which nothing can tail.
install -d -m 755 /etc/newrelic-infra/logging.d
cat >/etc/newrelic-infra/logging.d/dcss.yml <<'CONF'
logs:
  - name: syslog
    file: /var/log/syslog
  - name: auth
    file: /var/log/auth.log
  - name: dcss-backup
    file: /var/log/dcss-backup.log
CONF

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq newrelic-infra
systemctl enable --now newrelic-infra
systemctl restart newrelic-infra
echo "newrelic-infra $(dpkg-query -W -f='${Version}' newrelic-infra) running; the host appears at one.newrelic.com > Infrastructure > Hosts within a minute"

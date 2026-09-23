# Oracle Cloud deployment

1. Create an Always Free instance: image Ubuntu 24.04 (aarch64), shape VM.Standard.A1.Flex, 2 OCPU / 12 GB
   (the current Always Free ceiling), your SSH key. Under Management paste `cloud-init.yaml`.
2. Networking: in the VCN's default security list add ingress rules for TCP 80, TCP 443 and UDP 443 from 0.0.0.0/0.
3. DNS: `deploy/oci/dns.sh <public-ip>` creates the A record in Lightsail DNS (needs the local AWS login). Run it
   before the first start, or `docker compose restart caddy` afterwards so Caddy can pass the certificate challenge.
4. Check: `ssh ubuntu@<ip> 'cd /opt/dcss && docker compose ps && docker compose logs --tail 20'`, then open
   https://crawl.han.life and register the first account.
5. Backups: the one-time OCI setup and the NAS key below.

cloud-init only runs when the instance is created. To bring an existing VM up to date with this directory:
`scp compose.yaml Caddyfile backup.sh ubuntu@<ip>:/tmp/ && ssh ubuntu@<ip> 'sudo install -m 644 /tmp/compose.yaml /tmp/Caddyfile /opt/dcss/ && sudo install -m 755 /tmp/backup.sh /opt/dcss/ && cd /opt/dcss && docker compose up -d'`.

Updates: `cd /opt/dcss && docker compose pull && docker compose up -d && docker image prune -f`. Running games are
saved when the container stops. Every CI build is also pushed as `sha-<commit>`: to pin or roll back, put
`DCSS_TAG=sha-<commit>` in `/opt/dcss/.env` and run `docker compose up -d`; delete the line to follow `latest` again.

Admin: `docker exec dcss python3 webserver/wtutil.py password --reset <user>` prints a password reset link, and
`... wtutil.py ban --add|--hold|--clear <user>` manages bans. Both are stored in `/opt/dcss/data`.

Idle reclamation: Oracle may reclaim (stop) Always Free instances whose CPU, network and memory all stay under 20%
for 7 days, which this server always does. Upgrading the account to Pay As You Go keeps the same free limits and
removes that rule.

## Backups

- In-cloud: `backup.sh` runs nightly from `/etc/cron.d/dcss-backup` (18:17 UTC = 04:17 AEST / 05:17 AEDT, log in
  `/var/log/dcss-backup.log`) and puts a tarball of `/opt/dcss/data` into the Always Free Object Storage bucket
  `crawl-backup` (namespace `axnnb2qvhvxc`), authenticated as the instance. The account and settings databases are
  copied with SQLite's online backup, so they are consistent even while people play. Set `HC_PING_URL` in the cron
  file (e.g. a free healthchecks.io check) to get an alert when a night is missed.
  One-time setup, not in cloud-init: dynamic group `crawl-vm` with a matching rule on the compartment
  (`ALL {instance.compartment.id = '<compartment ocid>'}`, so a replacement instance still matches), policy
  `crawl-backup` with `Allow dynamic-group crawl-vm to manage objects in compartment <name> where
  target.bucket.name='crawl-backup'`, and a lifecycle rule on the bucket that deletes objects after 30 days.
- Restore (on the VM):

  ```sh
  cd /opt/dcss
  sudo /opt/oci/bin/oci os object list --auth instance_principal -bn crawl-backup --query 'data[].name' --output table
  sudo /opt/oci/bin/oci os object get --auth instance_principal -bn crawl-backup --name <file> --file /tmp/restore.tgz
  sudo docker compose stop dcss
  sudo mv data "data.pre-restore.$(date +%s)"
  sudo tar xzf /tmp/restore.tgz -C /opt/dcss   # as root, so the archive's uid 1000 ownership is kept
  sudo docker compose start dcss
  ```

- Off-cloud: the NAS pulls a copy over SSH with a key that can only read `/opt/dcss/data`. In
  `~ubuntu/.ssh/authorized_keys` on the VM:
  `restrict,command="rrsync -ro /opt/dcss/data" ssh-ed25519 AAAA... nas-backup` (`restrict` also blocks port
  forwarding, which matters because `ubuntu` is in the docker group). From DSM Task Scheduler as root:
  `rsync -a --delete -e "ssh -i /root/.ssh/crawl-backup -o IdentitiesOnly=yes" ubuntu@crawl.han.life:/ /volume1/docker/dcss-backup/`
  (rrsync roots the path at `/opt/dcss/data`, hence `:/`). `--delete` makes this a mirror: a wiped or damaged data
  directory on the VM reaches the NAS on the next run, so keep history on the NAS side, e.g. snapshots of the share
  (Snapshot Replication, Btrfs volumes only).

# Oracle Cloud deployment

1. Create an Always Free instance: image Ubuntu 24.04 (aarch64), shape VM.Standard.A1.Flex, 2 OCPU / 12 GB
   (the current Always Free ceiling), your SSH key. Under Management paste `cloud-init.yaml`.
2. Networking: in the VCN's default security list add ingress rules for TCP 80, TCP 443 and UDP 443 from 0.0.0.0/0.
3. DNS: `deploy/oci/dns.sh <public-ip>` swaps the current CNAME for an A record (needs the local AWS login). Run it
   before the first start, or `docker compose restart caddy` afterwards so Caddy can pass the certificate challenge.
4. Check: `ssh ubuntu@<ip> 'cd /opt/dcss && docker compose ps && docker compose logs --tail 20'`, then open
   https://crawl.han.life and register the first account.

Updates: `cd /opt/dcss && docker compose pull && docker compose up -d`. Data lives in `/opt/dcss/data`;
back it up with `rsync -a ubuntu@<ip>:/opt/dcss/data/ /volume1/docker/dcss-backup/` from the NAS.

Idle reclamation: Oracle deletes Always Free instances that stay under 20% CPU/network/memory for 7 days.
Upgrading the account to Pay As You Go keeps the same free limits and removes that rule.

# Helper scripts

Six sysadmin scripts for Luna to run and read back: machine health,
database backups to a NAS, missing security fixes, server updates and a
website security check. They're starting points: copy one into
`agent/jobs/`, change the address line at the top, and it works.

```bash
cp examples/jobs/web-health.sh agent/jobs/
nano agent/jobs/web-health.sh      # WEB=you@192.168.1.10 -> your server
bash agent/jobs/web-health.sh
```

`agent/jobs/` is gitignored, so your host names stay out of the repo,
and it's the only folder a scheduled job can run a script from.

| Script | What it does | Changes anything? |
|--------|--------------|-------------------|
| `vm-health.sh` | the machine her model runs on: load, memory, disks, the GPU (AMD), llama-server, failed services, errors since boot | no |
| `web-health.sh` | a web server: the basics, Apache and MariaDB, certificate renewal, every site Apache serves with its certificate's days left | no |
| `backups-to-nas.sh` | copies `*.sql.gz` dumps to a NAS share, checks each copy, thins out old ones. `--dry-run` | writes to the NAS only |
| `cve-check.sh` | security fixes each machine is missing (Debian, Ubuntu, Fedora, Arch; Unraid's version). `local` checks this computer | no |
| `web-update.sh` | lists waiting updates, then upgrades a Debian or Ubuntu server. `--check` only lists | yes: run it yourself in a terminal |
| `site-check.sh` | a website's security from outside, a fix for every finding (Apache, nginx or Plesk). `--active` adds ports and leaked files, `--report` prints a report to read | no |

`site-check.sh` needs no address: give it a domain. Use `--active` only
on your own sites, or a client's who said yes in writing.

**Linux only.** They're bash, built on Linux's own tools (systemd, apt
or dnf, `/proc`, `dig`, `nmap`), on the computer Luna runs on and the
machines they check.

**SSH keys, no passwords.** Every one logs in with `BatchMode=yes`, so
it fails instead of waiting for a password:

```bash
ssh-keygen -t ed25519
ssh-copy-id you@192.168.1.10
ssh -o BatchMode=yes you@192.168.1.10 hostname   # must print a name without asking
```

Then make one a one-sentence check with a
[recipe](../../docs/skills.md#walkthrough-check-vm-health), or run it on
a timer as a [scheduled job](../../docs/jobs.md). More on each, and the
recipe for website scans: [Sysadmin](../../docs/sysadmin.md#helper-scripts).

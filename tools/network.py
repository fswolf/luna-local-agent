"""find_device and scan_network: machines on your own network, by name.

    > "Find the Unraid server."
    > "What's the address of my MewNix desktop?"
    > "What's on the network?"

Nothing here needs root, nmap or a new package. Addresses come from what
the computer already knows and a few quiet lookups:

1. The neighbor (ARP) table: `ip neigh`, or `arp -a` on macOS and Windows.
2. A wake-up pass over your own /24: one empty UDP packet to each address
   makes the kernel ask "who has this IP?", and every machine that's on
   answers that, even the ones that ignore ping. Nothing is port scanned.
3. Names: name.local (mDNS: Unraid, Macs, avahi desktops, printers), the
   router's DNS, and reverse lookups of what answered.

Remembering is long-term memory, not a list in config: when she finds
something she offers to save a fact like "Ryan's Unraid server has MAC
aa:bb:cc:dd:ee:ff", and next time that MAC is matched wherever DHCP has
moved it. MACs don't change; IPs do.

Only private addresses (192.168, 10, 172.16-31) are ever touched.
Device names are written by whoever set the device up, so they are
cleaned down to plain characters before the model sees them.
"""
import concurrent.futures as futures
import ipaddress
import os
import re
import socket
import subprocess
import sys
import time

from . import tool

_MAC = re.compile(r"\b([0-9a-f]{1,2}(?:[:-][0-9a-f]{1,2}){5})\b", re.I)
_IP = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_last = {"at": 0.0, "found": {}}     # one scan is reused for a minute


def _mac(text):
    """aa:bb:cc:dd:ee:ff, from any of the ways systems print one."""
    parts = re.split(r"[:-]", text.strip().lower())
    return ":".join(p.zfill(2) for p in parts) if len(parts) == 6 else ""


def _private(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False

    return a.version == 4 and a.is_private and not (a.is_loopback or a.is_link_local or a.is_multicast)


def _clean(name):
    """A device's own name, made safe to show the model."""
    name = re.sub(r"[^A-Za-z0-9._ -]", "", str(name or ""))[:48].strip(" .")
    return name


def _run(cmd):
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=flags).stdout
    except Exception:
        return ""


def _neighbors():
    """{ip: mac} the computer already knows."""
    out = {}

    if sys.platform.startswith("linux"):
        text = _run(["ip", "-4", "neigh"])

        for line in text.splitlines():
            ip, mac = _IP.search(line), re.search(r"lladdr\s+(\S+)", line)

            if ip and mac and "FAILED" not in line and "INCOMPLETE" not in line:
                out[ip.group(1)] = _mac(mac.group(1))

        if not text:                                   # no iproute2: the kernel's own table
            try:
                with open("/proc/net/arp") as f:
                    for line in f.read().splitlines()[1:]:
                        bits = line.split()
                        if len(bits) >= 4 and bits[3] != "00:00:00:00:00:00":
                            out[bits[0]] = _mac(bits[3])
            except OSError:
                pass
    else:                                              # macOS and Windows
        for line in _run(["arp", "-a"]).splitlines():
            ip, mac = _IP.search(line), _MAC.search(line)

            if ip and mac:
                out[ip.group(1)] = _mac(mac.group(1))

    return {ip: mac for ip, mac in out.items()
            if _private(ip) and mac and mac != "ff:ff:ff:ff:ff:ff" and not mac.startswith("01:00:5e")}


def _my_ip():
    """This computer's LAN address. Connecting a UDP socket sends nothing;
    it only asks the OS which interface it would use."""
    for probe in ("192.168.0.1", "10.0.0.1", "172.16.0.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((probe, 9))
            ip = s.getsockname()[0]
            s.close()

            if _private(ip):
                return ip
        except OSError:
            pass

    return ""


def _wake(mine):
    """One empty UDP packet to every address in our /24, so the kernel
    ARPs for each and the neighbor table fills in. Then a moment for the
    answers to arrive."""
    net = ipaddress.ip_network(mine + "/24", strict=False)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        for host in net.hosts():
            if str(host) != mine:
                try:
                    s.sendto(b"", (str(host), 9))      # 9 = discard
                except OSError:
                    pass
    finally:
        s.close()

    time.sleep(2.0)


def _reverse(ips):
    """{ip: name} from reverse DNS, all at once, given three seconds."""
    names = {}
    pool = futures.ThreadPoolExecutor(max_workers=32)
    jobs = {pool.submit(socket.gethostbyaddr, ip): ip for ip in ips}

    try:
        for job in futures.as_completed(jobs, timeout=3):
            try:
                name = _clean(job.result()[0])
                if name and not _IP.fullmatch(name):
                    names[jobs[job]] = name
            except Exception:
                pass
    except futures.TimeoutError:
        pass

    pool.shutdown(wait=False, cancel_futures=True)
    return names


def _resolve(name):
    """name -> IPs, via the router's DNS and mDNS (.local)."""
    base = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
    tries = [base] if base.endswith(".local") else [base, base + ".local"]
    found = {}

    def look(host):
        try:
            return host, {a[4][0] for a in socket.getaddrinfo(host, None, socket.AF_INET)}
        except OSError:
            return host, set()

    if not base:
        return found

    pool = futures.ThreadPoolExecutor(max_workers=2)

    try:
        for job in futures.as_completed([pool.submit(look, h) for h in tries], timeout=4):
            host, ips = job.result()
            for ip in ips:
                if _private(ip):
                    found.setdefault(ip, host)
    except futures.TimeoutError:
        pass

    pool.shutdown(wait=False, cancel_futures=True)
    return found


def _scan(fresh=False):
    """{ip: {"mac", "name"}} for everything on the LAN."""
    if not fresh and time.monotonic() - _last["at"] < 60 and _last["found"]:
        return _last["found"]

    mine = _my_ip()

    if mine:
        _wake(mine)

    table = _neighbors()
    names = _reverse(list(table) + ([mine] if mine else []))
    found = {ip: {"mac": mac, "name": names.get(ip, "")} for ip, mac in table.items()}

    if mine:
        found[mine] = {"mac": "", "name": (names.get(mine) or _clean(socket.gethostname())) + " (this computer)"}

    _last.update(at=time.monotonic(), found=found)
    return found


def _note(mac):
    """Phones and laptops on Wi-Fi often use a made-up MAC per network."""
    try:
        return " (private Wi-Fi address, may change)" if int(mac.split(":")[0], 16) & 2 else ""
    except (ValueError, IndexError):
        return ""


def _remembered(words):
    """MACs and IPs from long-term memory facts that mention these words."""
    try:
        from mind import longterm

        facts = longterm.get_facts()
    except Exception:
        return []

    hits = []

    for fact in facts:
        low = fact.lower()

        if words and all(w in low for w in words):
            for m in _MAC.findall(fact):
                hits.append(("mac", _mac(m), fact))
            for ip in _IP.findall(fact):
                if _private(ip):
                    hits.append(("ip", ip, fact))

    return hits


def _owner():
    """'Shannon's' for the example fact, or 'The user's'."""
    try:
        import config

        return f"{config.USER_NAME}'s" if config.USER_NAME else "The user's"
    except Exception:
        return "The user's"


def _row(ip, info):
    name = info.get("name") or "no name"
    mac = info.get("mac") or ""
    return f"- {ip}  {name}" + (f"  [{mac}]{_note(mac)}" if mac else "")


@tool(
    "find_device",
    "Find a machine on the user's home network and give its IP address: by name ('unraid', "
    "'my desktop', 'the printer') or by MAC address. Checks what has been remembered first, then "
    "the network's own names (.local, the router), then looks around the local network.",
    {
        "name": {"type": "string", "description": "What the user calls it, a hostname, or a MAC address."},
    },
    required=("name",),
)
def _find_device(name):
    name = str(name or "").strip()
    asked_mac = _MAC.search(name)
    words = [w for w in re.findall(r"[a-z0-9]+", name.lower())
             if w not in {"my", "the", "a", "server", "pc", "computer", "box", "machine"}] or \
        re.findall(r"[a-z0-9]+", name.lower())

    lines = []
    want_macs = {_mac(asked_mac.group(1))} if asked_mac else set()

    # 1. Long-term memory: a remembered MAC finds it wherever it has moved.
    for kind, value, fact in ([] if asked_mac else _remembered(words)):
        if kind == "mac":
            want_macs.add(value)
        else:
            lines.append(f"- {value}  remembered: {fact!r} (not checked)")

    # 2. Its own name on the network: the whole thing, then each word ("mewnix desktop" -> mewnix).
    if not asked_mac:
        for guess in dict.fromkeys([" ".join(words) or name] + [w for w in words if len(w) > 2]):
            for ip, host in _resolve(guess).items():
                if not any(l.startswith(f"- {ip} ") for l in lines):
                    lines.append(f"- {ip}  {host}  (answers to that name)")

    # 3. Look around.
    found = _scan(fresh=bool(want_macs) and not lines)

    for ip, info in sorted(found.items(), key=lambda kv: tuple(int(p) for p in kv[0].split("."))):
        by_mac = info["mac"] in want_macs
        by_name = words and all(w in info["name"].lower().replace("-", "") or w in info["name"].lower()
                                for w in words)

        if by_mac or (by_name and not asked_mac):
            row = _row(ip, info) + ("  (remembered MAC)" if by_mac and not asked_mac else "")
            if not any(l.startswith(f"- {ip} ") for l in lines):
                lines.append(row)

    if not lines:
        if want_macs:
            return (f"Remembered MAC {', '.join(sorted(want_macs))} for {name!r}, but nothing with that MAC "
                    "answered just now. It may be off or asleep.")

        return (f"Nothing on the network calls itself {name!r}. Run scan_network to see everything "
                "that's on, and ask the user which one it is.")

    remember = "" if want_macs else (
        " If the user confirms which one it is, offer to remember it with remember_fact, including its "
        f"MAC address (e.g. \"{_owner()} Unraid server has MAC aa:bb:cc:dd:ee:ff\"), so it's found even after "
        "its IP changes.")

    return "\n".join(lines) + ("\n" + remember.strip() if remember else "")


@tool(
    "scan_network",
    "List the machines on the user's home network right now: IP address, name if it has one, MAC. "
    "Takes a few seconds. Use find_device instead when looking for one machine by name.",
    {},
)
def _scan_network():
    found = _scan(fresh=True)

    if not found:
        return "Couldn't see the local network from here (no LAN address, or the neighbor table is empty)."

    rows = [_row(ip, info) for ip, info in
            sorted(found.items(), key=lambda kv: tuple(int(p) for p in kv[0].split(".")))]
    named = sum(1 for i in found.values() if i["name"])

    return (f"{len(found)} on the network, {named} with a name:\n" + "\n".join(rows[:80])
            + ("\n(and more)" if len(rows) > 80 else "")
            + "\nUnnamed ones can be identified by asking the user, then remembered with remember_fact "
              "including the MAC.")

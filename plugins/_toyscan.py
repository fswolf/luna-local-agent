"""Finding the toy servers on your network: Intiface Central (Buttplug)
and the Lovense Remote app in Game Mode, for /buttplug find and
/lovense find.

    1. This computer first (127.0.0.1), then every machine on your own
       network: the same quiet wake-up pass find_device uses, then the
       addresses the computer knows (tools/network.py).
    2. A quick TCP knock on the port each app uses: 12345 for Intiface,
       20010 (http) and 30010 (https) for Lovense Remote.
    3. Only what answers like the app counts: a Buttplug handshake for
       Intiface, a GetToys answer for Lovense. Anything else on the port
       is ignored.

Only private addresses are touched, and nothing is port scanned beyond
those three ports. Not a plugin itself: the leading underscore keeps the
loader away.
"""
import ipaddress
import json
import socket
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor

INTIFACE_PORT = 12345
LOVENSE_HTTP, LOVENSE_HTTPS = 20010, 30010


def hosts(wake=True):
    """This computer, then the machines on the network, private addresses only."""
    found = ["127.0.0.1"]
    try:
        from tools import network

        mine = network._my_ip()
        if mine:
            found.append(mine)
            if wake:
                network._wake(mine)
        found += sorted(network._neighbors(), key=lambda ip: ipaddress.ip_address(ip))
    except Exception:
        pass
    out = []
    for ip in found:
        if ip not in out and (ip == "127.0.0.1" or _private(ip)):
            out.append(ip)
    return out


def _private(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.version == 4 and a.is_private and not (a.is_loopback or a.is_link_local)


def _knock(ip, port, timeout=0.5):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def open_on(ips, port):
    """The addresses with something listening on port."""
    with ThreadPoolExecutor(max_workers=32) as pool:
        return [ip for ip, ok in zip(ips, pool.map(lambda ip: _knock(ip, port), ips)) if ok]


def _intiface_at(ip):
    """'Intiface Central' (its server name) if a Buttplug server answers here, else ''."""
    try:
        import websocket
    except ImportError:
        return ""
    url = f"ws://{ip}:{INTIFACE_PORT}"
    try:
        ws = websocket.create_connection(url, timeout=3)
    except Exception:
        return ""
    try:
        ws.send(json.dumps([{"RequestServerInfo": {"Id": 1, "ClientName": "Luna (looking)",
                                                   "MessageVersion": 3}}]))
        reply = json.loads(ws.recv())
        info = (reply[0] if isinstance(reply, list) and reply else {}).get("ServerInfo") or {}
        return str(info.get("ServerName") or "Buttplug server")[:60] if info else ""
    except Exception:
        return ""
    finally:
        try:
            ws.close()
        except Exception:
            pass


def find_intiface(wake=True):
    """[(url, server name)] for every Buttplug server on the network."""
    ips = open_on(hosts(wake), INTIFACE_PORT)
    with ThreadPoolExecutor(max_workers=8) as pool:
        names = list(pool.map(_intiface_at, ips))
    return [(f"ws://{ip}:{INTIFACE_PORT}", name) for ip, name in zip(ips, names) if name]


def _lovense_at(host, port, https):
    """The toy names if Lovense Remote answers GetToys here, else None."""
    scheme = "https" if https else "http"
    req = urllib.request.Request(f"{scheme}://{host}:{port}/command",
                                 data=json.dumps({"command": "GetToys"}).encode(),
                                 headers={"Content-Type": "application/json", "X-platform": "Luna"})
    try:
        with urllib.request.urlopen(req, timeout=3, context=ssl.create_default_context() if https else None) as r:
            reply = json.loads(r.read().decode() or "{}")
    except Exception:
        return None
    if not isinstance(reply, dict) or str(reply.get("code", 200)) != "200":
        return None
    toys = (reply.get("data") or {}).get("toys") or {}
    if isinstance(toys, str):
        try:
            toys = json.loads(toys)
        except ValueError:
            toys = {}
    return [t.get("nickName") or t.get("name") or tid for tid, t in (toys.items() if isinstance(toys, dict) else [])]


def find_lovense(wake=True):
    """[(host, port, use_https, [toy names])] for every Lovense Remote in
    Game Mode. Its https address is the app's own lovense.club name for
    the IP (192-168-0-5.lovense.club), which needs working DNS."""
    ips = hosts(wake)
    found = []
    for ip in open_on(ips, LOVENSE_HTTP):
        toys = _lovense_at(ip, LOVENSE_HTTP, False)
        if toys is not None:
            found.append((ip, LOVENSE_HTTP, False, toys))
    for ip in open_on(ips, LOVENSE_HTTPS):
        if any(f[0] == ip for f in found):
            continue
        host = ip.replace(".", "-") + ".lovense.club"
        toys = _lovense_at(host, LOVENSE_HTTPS, True)
        if toys is not None:
            found.append((host, LOVENSE_HTTPS, True, toys))
    return found

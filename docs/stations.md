# Relay stations: talk to her from another room

An old phone or tablet becomes a way to talk to Luna from the kitchen, the
bedroom, anywhere in the house. It runs nothing of its own: it opens a page
Luna serves on your home network, you tap and talk, and she answers through
its speaker. It's the same Luna as at the desk: same memory, mood, people
and tools. Nothing to install on the device, no account, no internet needed.

<img width="300" alt="A phone as a relay station in the kitchen: one big Tap to talk button, what you said, and her answer underneath" src="https://raw.githubusercontent.com/fswolf/luna-local-agent/main/assets/relay-station.jpg" />

## Set it up

1. Install the extra once (it makes the certificates and the QR codes):

   ```bash
   python3 installer/install.py --extras stations
   ```

2. Open the settings page (`/settings`), find **Relay stations** and switch
   **enabled** on. She starts listening on your home network: port 8793 for
   the stations and 8794 for the setup page (`station.port` changes them).
3. Type a name for the device (kitchen, bedroom) and press **Add a phone or
   tablet**. A QR code appears.
4. On the phone or tablet, scan it with the camera. The setup page walks
   you through two steps:
   - **Trust Luna's certificate** (once per device). Phones only allow the
     microphone on secure pages, so Luna made her own certificate on your
     PC. Download it and follow the steps for Android or iPhone/iPad shown
     there.
   - **Open Luna.** The device is paired and the page opens. Bookmark it or
     add it to the home screen; from then on it opens straight to her.

The pairing code works once, for 15 minutes. Paired devices are listed
under Relay stations, each with **Unpair**.

A paired device stays paired until you unpair it. Its cookie is renewed
every time it opens Luna, and the page keeps its own copy of the device's
token, so a browser that throws cookies away when it closes (Firefox can)
reconnects by itself. Opening the old pairing link again on a paired
device just goes straight in.

## Talking

Tap the big button and talk. She stops listening after a short pause (or
tap again). What she heard shows under the button, her reply appears as
she writes it, and her voice plays on the device, sentence by sentence.
The PC shows the turn too, marked with the room: `[kitchen] ...`.

If she wants to do something that needs your OK (write a file, run a
command), the question appears on the device that asked, with **Allow**
and **Deny**. Unanswered for two minutes means no.

While a voice enrolment is running at the PC (`/people enroll voice`), the
stations wait: read the enrolment lines at the PC.

## Your computer

- **Windows:** the first time, Windows Firewall asks whether Python may
  accept connections. Allow it on **private networks**.
- **macOS:** if the firewall is on, allow incoming connections for Python
  once.
- **Linux (Fedora and others with firewalld):** the ports are blocked until
  opened. The settings page shows the command, once:

  ```bash
  sudo firewall-cmd --permanent --add-port=8793-8794/tcp && sudo firewall-cmd --reload
  ```

- The PC has to be awake. A device asleep or off the Wi-Fi can't reach her.
- If your router gives the PC a new address, Luna makes a new certificate
  for it on the next start (the device doesn't need pairing again, but the
  bookmark's address changes). Reserving the PC's address in the router
  avoids that.

## The device

- **Android:** use Chrome. Firefox only trusts the certificate with its
  "use third-party CA certificates" option.
- **iPhone/iPad:** Safari. Both certificate steps on the setup page are
  needed (installing the profile, then switching on full trust).
- Keep it plugged in. The page asks the screen to stay on while it's open.

## Safety

- Off until you switch it on. When on, it answers home-network addresses
  only (private, link-local, loopback), never the internet.
- A device needs a pairing code made on this PC. After pairing it keeps a
  token (a cookie, and a copy in the page's own storage), stored on the PC
  only as a hash. Unpairing removes it: a device that comes back with an
  unpaired token is told to pair again, and its copy is dropped.
- Luna's certificate authority is made on your PC and its key never leaves
  it (`~/.config/ai-voice/station/`). It can only vouch for home-network
  addresses and `.local` names, so even someone with the key couldn't pass
  off a real website to a device that trusts it.
- Permission questions are always asked on the device, never answered for
  you.

## Experimental: ESPHome voice satellites

> **Untested on real hardware.** Written from the libraries' documentation
> and Home Assistant's own code, not yet run against a device. Expect rough
> edges, and please report what happens.

Dedicated voice devices that run ESPHome can be stations too, with no Home
Assistant in between: FutureProofHomes' **Satellite1**, Home Assistant's
**Voice Preview Edition**, a **ReSpeaker Lite**, an ESP32-S3-BOX. They
hear their own wake word ("Okay Nabu", "Hey Jarvis"...), cancel their own
echo and have proper room microphones. Luna connects to each one the way
Home Assistant would, takes the audio straight from it (so she knows whose
voice it is), answers, and tells the device where to fetch her reply.

1. Install the extra: `python3 installer/install.py --extras satellites`.
2. Relay stations must be switched on (the device fetches her reply from
   the setup port, 8794).
3. List the devices in `config.json`, with each one's API encryption key
   (from its ESPHome config, or the Home Assistant device page):

   ```json
   "station": {
       "enabled": true,
       "satellites": [
           {"name": "kitchen", "host": "192.168.0.50", "key": "base64 key from the device"}
       ]
   }
   ```

4. Restart Luna. The settings page lists each satellite under Relay
   stations with its status.

A device answers one controller at a time: remove it from Home Assistant
(or stop Home Assistant using its voice) while Luna has it. With no screen,
she declines anything that needs your permission on these devices.

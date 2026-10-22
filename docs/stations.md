# Relay stations: talk to her from another room

An old phone or tablet becomes a way to talk to Luna from the kitchen, the
bedroom, anywhere in the house. It runs nothing of its own: it opens a page
Luna serves on your home network, you tap and talk, and she answers through
its speaker. It's the same Luna as at the desk: same memory, mood, people
and tools. Nothing to install on the device, no account, no internet needed.

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
  token, stored on the PC only as a hash. Unpairing removes it.
- Luna's certificate authority is made on your PC and its key never leaves
  it (`~/.config/ai-voice/station/`). It can only vouch for home-network
  addresses and `.local` names, so even someone with the key couldn't pass
  off a real website to a device that trusts it.
- Permission questions are always asked on the device, never answered for
  you.

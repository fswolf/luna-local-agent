#!/usr/bin/env bash
# cam-led.sh [off|on|auto] [/dev/videoN]  - try to switch a webcam's light.
# Only works where the camera lets software drive its LED (mostly Logitech
# UVC cams, some others). Many cams wire the LED to the sensor's power: then
# no program can turn it off, and this says so instead of pretending.
set -u
want=${1:-off}; only=${2:-}
case $want in off) v=0; u=0;; on) v=1; u=1;; auto) v=3; u=3;; *) echo "usage: $0 [off|on|auto] [/dev/videoN]"; exit 2;; esac
command -v v4l2-ctl >/dev/null || { echo "needs v4l2-ctl: sudo dnf install v4l-utils"; exit 1; }
did=0

for dev in ${only:-/dev/video*}; do
  [ -e "$dev" ] || continue
  v4l2-ctl -d "$dev" --all 2>/dev/null | grep -q "Video Capture" || continue   # skip metadata nodes
  name=$(v4l2-ctl -d "$dev" --info 2>/dev/null | sed -n 's/.*Card type *: //p')
  ctl=$(v4l2-ctl -d "$dev" -L 2>/dev/null | grep -io '^ *led[a-z0-9_]*mode' | head -1 | tr -d ' ')
  if [ -n "$ctl" ]; then
    # menu: 0 off, 1 on, 2 blink, 3 auto (Logitech); some only have 0/1
    v4l2-ctl -d "$dev" -c "$ctl=$v" 2>/dev/null || v4l2-ctl -d "$dev" -c "$ctl=$(( v > 1 ? 1 : v ))" \
      && { echo "$dev ($name): $ctl -> $want"; did=1; continue; }
  fi
  if command -v uvcdynctrl >/dev/null && uvcdynctrl -d "${dev#/dev/}" -c 2>/dev/null | grep -q "LED1 Mode"; then
    uvcdynctrl -d "${dev#/dev/}" -s "LED1 Mode" "$u" && { echo "$dev ($name): LED1 Mode -> $want (uvcdynctrl)"; did=1; continue; }
  fi
  echo "$dev ($name): no LED control exposed"
done

# a few laptops put the camera light under /sys/class/leds
for l in /sys/class/leds/*{cam,video}*; do
  [ -e "$l/brightness" ] || continue
  b=$([ "$want" = off ] && echo 0 || cat "$l/max_brightness")
  if echo "$b" | sudo tee "$l/brightness" >/dev/null; then echo "$l -> $want"; did=1; fi
done

[ $did = 1 ] || { echo "nothing to switch: this camera's light is hardwired to the sensor (on whenever it's in use)."
                  echo "Logitech cams may only show it after: uvcdynctrl -i /usr/share/uvcdynctrl/data/046d/logitech.xml"; exit 1; }

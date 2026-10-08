// Where she looks, for both portraits (Live2D and VRM).
//
// Everything here is in plain units: x and y from -1 to 1, x towards the
// right of the screen, y up. Each renderer scales them to its own angles.
//
//   base      where "you" are - Luna's terminal, from the server's gaze
//             events (Hyprland), or straight ahead when that's unknown
//   talking   eyes on you, with the small darts real eyes make
//   idle      mostly towards you, wandering off now and then
//   thinking  up and away to one side, a look down while she weighs it,
//             a switch of sides, a quick check back at you - with little
//             eye darts on top, the head wandering, tilted, brow up

const rand = (a, b) => a + Math.random() * (b - a);
const clamp = v => Math.max(-1, Math.min(1, +v || 0));

export function createLook() {
  const s = {
    stage: 'idle', tx: 0, ty: 0, next: 0, side: 1,
    base: { x: 0, y: 0, known: false },
    dart: { x: 0, y: 0, next: 0 },
  };

  function setTarget(ev) {
    s.base = ev.none ? { x: 0, y: 0, known: false }
                     : { x: clamp(ev.x), y: clamp(ev.y), known: true };
    if (s.stage !== 'thinking') s.next = 0;   // turn to it now, not at the next glance
  }

  function setStage(stage) {
    if (stage === s.stage) return;
    s.stage = stage;
    s.next = 0;

    if (stage === 'thinking') {
      // Away from you, the way people look off to think - or either
      // side when she doesn't know where you are.
      s.side = s.base.known && Math.abs(s.base.x) > 0.2 ? -Math.sign(s.base.x)
                                                       : (Math.random() < 0.5 ? 1 : -1);
    }
  }

  function glance(strength = 1, now = performance.now() / 1000) {
    s.tx = rand(-0.9, 0.9) * strength;
    s.ty = rand(-0.2, 0.5) * strength;
    s.next = now + rand(0.6, 1.4);
  }

  function pick(now) {
    const b = s.base;

    if (s.stage === 'thinking') {
      const r = Math.random();

      if (r < 0.55) {                       // up and to the side
        s.tx = s.side * rand(0.45, 0.9); s.ty = rand(0.4, 0.8); s.next = now + rand(1.2, 2.8);
      } else if (r < 0.72) {                // down, weighing it up
        s.tx = s.side * rand(0, 0.3); s.ty = rand(-0.6, -0.35); s.next = now + rand(0.8, 1.6);
      } else if (r < 0.86) {                // the other side
        s.side = -s.side;
        s.tx = s.side * rand(0.45, 0.85); s.ty = rand(0.35, 0.75); s.next = now + rand(1.0, 2.2);
      } else {                              // a quick check back at you
        s.tx = b.x; s.ty = b.y; s.next = now + rand(0.4, 0.8);
      }
    } else if (s.stage === 'listening' || s.stage === 'speaking') {
      s.tx = b.x * 0.9 + rand(-0.1, 0.1);
      s.ty = b.y * 0.9 + rand(-0.05, 0.08);
      s.next = now + rand(0.5, 1.6);
    } else {
      const away = Math.random() < 0.3;
      s.tx = away ? rand(-1, 1) : b.x * 0.7 + rand(-0.15, 0.15);
      s.ty = away ? rand(-0.35, 0.45) : b.y * 0.7 + rand(-0.06, 0.1);
      s.next = now + (away ? rand(0.8, 2.0) : rand(1.0, 3.5));
    }
  }

  // -> { x, y }       where the eyes go (-1..1)
  //    headGain       how much of that the head follows (1 = as before)
  //    wander {x, y}  extra slow head drift, same units as x/y
  //    tilt           head tilt, -1..1
  //    brow, purse    small face offsets while thinking
  function update(now) {
    if (now >= s.next) pick(now);

    const thinking = s.stage === 'thinking';

    if (thinking && now >= s.dart.next) {
      s.dart.x = rand(-0.1, 0.1); s.dart.y = rand(-0.06, 0.06); s.dart.next = now + rand(0.25, 0.6);
    } else if (!thinking) {
      s.dart.x = s.dart.y = 0;
    }

    return {
      x: clamp(s.tx + s.dart.x),
      y: clamp(s.ty + s.dart.y),
      headGain: thinking ? 1.25 : 1,
      wander: thinking ? { x: Math.sin(now * 0.5) * 0.22 + Math.sin(now * 0.23 + 2) * 0.12,
                           y: Math.sin(now * 0.37 + 1) * 0.12 }
                       : { x: 0, y: 0 },
      tilt: thinking ? s.side * 0.9 + Math.sin(now * 0.6) * 0.25 : 0,
      brow: thinking ? 0.35 : 0,
      purse: thinking ? -0.25 : 0,
      thinking,
    };
  }

  return { setTarget, setStage, glance, update, state: s };
}

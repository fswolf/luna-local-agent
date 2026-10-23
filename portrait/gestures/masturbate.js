// masturbate: touch_self for 20 s (twice through) into pant - a sweat drop
// as she catches her breath, then hearts. Heated; she does it when she
// writes it. The sound (moan-orgasm.mp3, 27.5 s) builds with her and
// peaks about 19 s in, as the second touch_self ends.
export default {
  chain: ['touch_self', 'touch_self', 'pant'],
  sound: 'moan-orgasm',
  emote: [{ name: 'sweat', at: 20 }, { name: 'hearts', at: 23.2 }],   // hearts once the sweat drop is gone
  keywords: ["masturbates", "pleasures herself", "gets herself off", "touches herself until"],
  about: "lewd, heated: touches herself until she's spent, then out of breath",
  private: true,      // never from stream chat
  lewd: true,         // held back on a stream where lewd is off (twitch/youtube "lewd": false)
  touch: ['groin'], moods: ['heated'],
};

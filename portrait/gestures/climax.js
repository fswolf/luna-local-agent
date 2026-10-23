// climax: touch_self building into pant - she peaks, then is left out of
// breath, bent over, and gets it back with a long sigh. Two gestures chained;
// the sound (moan-climax.mp3) is the loudest 11 s of the old touch-self.mp3,
// fading as she recovers. Heated only.
export default {
  chain: ['touch_self', 'pant'],
  sound: 'moan-climax',
  lights: [[0, 0], [3, 0.4], [8, 0.9], [9.5, 1.4], [11, 0.5], [16, 0.15]],   // her light strips throb with it (build, peak, fade)
  keywords: ["climaxes", "orgasm", "comes undone", "shudders and moans"],
  about: "lewd, heated: peaks, then left out of breath",
  private: true,      // never from stream chat
  lewd: true,         // held back on a stream where lewd is off (twitch/youtube "lewd": false)
  touch: ['groin'], moods: ['heated'],
};

# Music: she listens and dances

Play a song and Luna can hear what kind it is and where its beat falls. She
can talk about it ("ooh, dub techno"), dance to energetic music on her
portrait in time with it, bob her head to calm songs, and sometimes bring
out her rave set (pacifier and glow sticks) for rave styles. The glow sticks
pulse on the beat.

Optional and off by default. The listening runs as a small service on her
server (or the same PC), the way her model server does. Her desktop only
records a short clip and asks.

## How it works

1. When your player (anything `playerctl` sees: Spotify, a browser tab,
   mpv...) starts a new track, she waits about 10 seconds to get past the
   intro.
2. She records 8 seconds of what your speakers are playing. That's the sound
   card's monitor, never the microphone, and not while she's talking.
3. She sends the clip to the listening service, which answers in about half
   a second:
   - music, talking, or talking over music
   - the style, from 400 Discogs styles (techno, dubstep, drum and bass, trap...)
   - the tempo, where the beats fall, and how heavy the bass is
4. That's one look per track. A song that comes back within half an hour
   isn't listened to again.

The clip is sent once and thrown away. Nothing leaves your network.

| She hears | She does |
|---|---|
| Energetic music (fast, or a rave style) | Dances when she's idle and in the mood, matched to the song's tempo, with short breaks where she just nods on the beat |
| Rave styles (techno, house, trance, dubstep, DnB, hardstyle, trap...) | Sometimes puts on her rave set; it comes off when the music stops |
| A calm song | Nods her head on the beat |
| Talking (a vlog, a podcast) | Nothing: it isn't music |

She doesn't dance while you're talking to her, while she's asleep or holding
her coffee, book or plushie, or in the lewd or grudge moods.

## Setting it up

On her server (the machine running llama.cpp), from Luna's folder:

```bash
server/music/install.sh
```

It puts a Python venv and the style model in `~/.local/share/luna-listen`,
checks itself with a made-up 128 BPM beat, and starts a `luna-listen`
service on port 8795 that comes back on boot. It ends with the line to
type into Luna:

```
/set music.url http://192.168.0.186:8795
```

Use `--no-service` to run it yourself instead, `--port` for another port, and
`remove` to take the service away again. To run it on the same PC as Luna,
use the same steps and `/set music.url http://127.0.0.1:8795`.

On the desktop she needs `playerctl`, plus `parec` (PipeWire or PulseAudio)
or `ffmpeg` to record.

## Settings

| Setting | Default | What it does |
|---|---|---|
| `music.url` | empty (off) | The listening service |
| `music.after` | 10 | Seconds into a track before she listens |
| `music.seconds` | 8 | Seconds she records (3-20) |
| `music.dance` | true | Dance and nod on her portrait |
| `music.rave` | true | Rave styles sometimes bring out the rave set |

`/music` shows what she heard. `/music now` listens again.

## The style model

The style model is Discogs-EffNet by the Music Technology Group (Universitat
Pompeu Fabra), run with onnxruntime. Its licence is **CC BY-NC-SA 4.0: free
for personal and open-source use, not for selling.** That's why the
installer downloads it rather than Luna shipping it. Without the model the
service still finds the tempo and beat, and guesses music from the beat
alone.

It knows Discogs' styles, so a very new or niche genre is named by its
nearest one (phonk, for example, isn't a Discogs style yet).

"""Presets: a few settings changed together, for what you mostly want her
for. Applied from the web settings page or /preset <name>; each value is
saved to config.json like any other change, so a preset is a starting
point, not a mode, and anything it set can be changed after.

Two kinds, which never touch the same settings, so one of each can be in
use at once:
  how she behaves   assistant, companion, streamer
  size ("kind": "size")   small, medium, large: what fits the model and its
                    context window (history kept word for word, facts and
                    notes per prompt, tools per turn, gestures offered, how
                    much of a page or command output she reads). Small is
                    the defaults, so it's the way back.
"""

PRESETS = {
    "assistant": {
        "label": "Assistant",
        "about": "Calm and to the point: moods turned down, no sulking, no emotes. A capable helper first.",
        "values": {
            "mood.enabled": True, "mood.intensity": 0.3, "mood.walk_away": False,
            "mood.emotes": False, "mood.affection": False, "mood.voice": False,
            "portrait.touch_talk": False, "situation.enabled": True, "self.greet": True,
        },
    },
    "companion": {
        "label": "Companion",
        "about": "Luna as designed: moods that move, a voice that follows them, emotes, and the right to walk away.",
        "values": {
            "mood.enabled": True, "mood.intensity": 1.0, "mood.walk_away": True,
            "mood.emotes": True, "mood.affection": True, "mood.voice": True,
            "portrait.touch_talk": True, "self.greet": True,
        },
    },
    "streamer": {
        "label": "Streamer",
        "about": "Lively on camera: a bit more expressive, chat can set off gestures, nothing lewd while live.",
        "values": {
            "mood.enabled": True, "mood.intensity": 1.2, "mood.walk_away": True,
            "mood.emotes": True, "mood.voice": True, "portrait.chat_gestures": True,
            "plugins.twitch.lewd": False, "plugins.youtube.lewd": False,
        },
    },

    # --- size: what fits the model. Rough guides, not limits: a 9B on a
    # server card with a 32k window can take medium. The tools pane shows
    # what each tool costs, for fine-tuning after.
    "small": {
        "kind": "size",
        "label": "Small model",
        "about": "4-9B, a window around 16k: the starting settings. Keeps prompts lean so tools and memory fit.",
        "values": {
            "history.max_raw_messages": 15, "history.summary_max_chars": 2500,
            "long_term_memory.context_facts": 25, "self.lessons_in_prompt": 4, "self.episodes_in_prompt": 2,
            "tools.routing": True, "tools.route_groups": 3, "tools.max_rounds": 4,
            "portrait.gestures_offered": 8,
            "web_search.max_results": 3, "web_search.page_max_chars": 6000,
            "web_search.research_max_chars": 9000, "shell.max_output_chars": 6000,
            "adaptive.first_budget": 1024, "generation.max_tokens": 4800,
        },
    },
    "medium": {
        "kind": "size",
        "label": "Medium model",
        "about": "Around 24B, or a small model with a 32k window: more history, memory and tools each turn.",
        "values": {
            "history.max_raw_messages": 30, "history.summary_max_chars": 4000,
            "long_term_memory.context_facts": 40, "self.lessons_in_prompt": 6, "self.episodes_in_prompt": 3,
            "tools.routing": True, "tools.route_groups": 5, "tools.max_rounds": 6,
            "portrait.gestures_offered": 10,
            "web_search.max_results": 5, "web_search.page_max_chars": 10000,
            "web_search.research_max_chars": 16000, "shell.max_output_chars": 10000,
            "adaptive.first_budget": 2048, "generation.max_tokens": 6000,
        },
    },
    "large": {
        "kind": "size",
        "label": "Large model",
        "about": "70B and up with a 64k+ window: every tool every turn, long history, deep reading.",
        "values": {
            "history.max_raw_messages": 50, "history.summary_max_chars": 6000,
            "long_term_memory.context_facts": 60, "self.lessons_in_prompt": 8, "self.episodes_in_prompt": 5,
            "tools.routing": False, "tools.route_groups": 5, "tools.max_rounds": 8,
            "portrait.gestures_offered": 12,
            "web_search.max_results": 6, "web_search.page_max_chars": 16000,
            "web_search.research_max_chars": 30000, "shell.max_output_chars": 16000,
            "adaptive.first_budget": 4096, "generation.max_tokens": 8000,
        },
    },
}


def kind(name):
    """"size" for the model-size presets, "use" for the rest."""
    return PRESETS[name].get("kind", "use")


def apply(name):
    """Save every value of a preset. Returns [(path, value, live)]; raises
    KeyError for an unknown preset."""
    import config

    preset = PRESETS[name]
    done = []

    for path, value in preset["values"].items():
        raw = ("true" if value else "false") if isinstance(value, bool) else str(value)
        saved, live = config.save_any(path, raw)
        done.append((path, saved, live))

    return done

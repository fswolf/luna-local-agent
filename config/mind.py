"""How she thinks and remembers: history, long-term memory, the thought
log, adaptive thinking, grounding, lessons, skills, projects, situation.

Part of the config package (it was one config.py); see config/__init__.py.
"""
from .base import setting

_history_cfg = setting("history", {})
MAX_RAW_MESSAGES = _history_cfg.get("max_raw_messages", 15)
SUMMARIZE_CHUNK = _history_cfg.get("summarize_chunk", 8)
# The running summary is re-compressed once it passes this, rather than
# being appended to forever.
SUMMARY_MAX_CHARS = int(_history_cfg.get("summary_max_chars", 2500))
# A full archive of every turn, which summarization never prunes. It is
# what search_history reads; the prompt never sees it.
TRANSCRIPT_ENABLED = bool(_history_cfg.get("transcript", True))
TRANSCRIPT_MAX_MB = float(_history_cfg.get("transcript_max_mb", 20))

_memory_cfg = setting("long_term_memory", {})
LONG_TERM_MEMORY_ENABLED = _memory_cfg.get("enabled", True)
LONG_TERM_MEMORY_MAX_FACTS = _memory_cfg.get("max_facts", 40)
# How many facts may go into one system prompt. Under this, all of them
# do; over it, the ones relevant to what was just said.
LONG_TERM_MEMORY_CONTEXT_FACTS = _memory_cfg.get("context_facts", 25)
# "json" is the original capped list in memory.json; "sqlite" is the
# experimental permanent table (mind/factstore.py) - uncapped, searched with
# FTS5, and able to retire a fact that stops being true instead of
# keeping both versions. Live: /set long_term_memory.backend json to
# fall back, and nothing is lost in either direction.
LONG_TERM_MEMORY_BACKEND = str(_memory_cfg.get("backend", "json"))

# The reasoning log - see mind/thoughtlog.py. Every turn from the keyboard
# or the mic keeps the model's scratchpad (<think> blocks, or the
# reasoning_content field) in agent/thoughts.db for review with
# /thoughts. Capped by record count; the oldest go first.
#   "thoughts": { "enabled": true, "max_records": 2000 }
_thoughts_cfg = setting("thoughts", {})
THOUGHTS_ENABLED = bool(_thoughts_cfg.get("enabled", True))
THOUGHTS_MAX_RECORDS = int(_thoughts_cfg.get("max_records", 2000))
# On llama-server, keep each token's probability too (and the runners-up
# when it was unsure). Nothing on LM Studio, which doesn't expose them.
THOUGHTS_TOKEN_PROBS = bool(_thoughts_cfg.get("token_probs", True))

# Adaptive thinking (llama-server only): a modest thinking budget for
# every turn, and a second, deeper look only when the reply came out
# shaky by its own token probabilities. See llm._rethink.
#   "adaptive": { "enabled": true, "first_budget": 1024, "deep_budget": -1,
#                 "rethink_below": 0.75, "min_gain": 0.05,
#                 "speak_corrections": true, "job_budget": 1024 }
# job_budget: the thinking budget for jobs and game turns (Zork, REALITI,
# Vibe City...), which get no second look. Unbounded, a game turn can
# think for minutes and look stalled. -1 = no limit.
_adaptive_cfg = setting("adaptive", {})
ADAPTIVE_ENABLED = bool(_adaptive_cfg.get("enabled", True))
ADAPTIVE_FIRST_BUDGET = int(_adaptive_cfg.get("first_budget", 1024))
ADAPTIVE_JOB_BUDGET = int(_adaptive_cfg.get("job_budget", 1024))
ADAPTIVE_DEEP_BUDGET = int(_adaptive_cfg.get("deep_budget", -1))
ADAPTIVE_RETHINK_BELOW = float(_adaptive_cfg.get("rethink_below", 0.75))
ADAPTIVE_MIN_GAIN = float(_adaptive_cfg.get("min_gain", 0.05))
ADAPTIVE_SPEAK_CORRECTIONS = bool(_adaptive_cfg.get("speak_corrections", True))
# "vote": on a shaky reply, ask again `votes` more times and go with what
# most of the answers agree on. "rethink": one deeper second look.
ADAPTIVE_MODE = str(_adaptive_cfg.get("mode", "vote")).lower()
ADAPTIVE_VOTES = int(_adaptive_cfg.get("votes", 2))

# The grounding check (mind/grounding.py): specifics she stated with nothing
# behind them. mode: "flag", "hedge" (default) or "check".
_grounding_cfg = setting("grounding", {})
GROUNDING_ENABLED = bool(_grounding_cfg.get("enabled", True))
GROUNDING_MODE = str(_grounding_cfg.get("mode", "hedge")).lower()
GROUNDING_HEDGE_LINE = str(_grounding_cfg.get(
    "hedge_line", "I haven't checked those details, though, so take them with a grain of salt."))
# "Let me read the file~" and then nothing: run the step she announced.
# Any backend, any of your turns that had tools - not just shaky ones.
FOLLOW_THROUGH = bool(_adaptive_cfg.get("follow_through", True))
ADAPTIVE_PREFIX = str(_adaptive_cfg.get("correction_prefix",
                                        "Hang on, let me correct that."))

# Growing up a little (mind/reflect.py, mind/notebook.py): lessons from her own
# mistakes, notes on each conversation, fact cleanup, saying when she's
# unsure, and picking up where the last session left off.
#   "self": { "lessons": true, "episodes": true, "tidy_facts": true,
#             "calibration": true, "greet": true, ... }
_self_cfg = setting("self", {})
SELF_LESSONS = bool(_self_cfg.get("lessons", True))
SELF_LESSONS_IN_PROMPT = int(_self_cfg.get("lessons_in_prompt", 4))
SELF_MAX_LESSONS = int(_self_cfg.get("max_lessons", 40))
SELF_REFLECT_HOURS = float(_self_cfg.get("reflect_every_hours", 20))
SELF_EPISODES = bool(_self_cfg.get("episodes", True))
SELF_EPISODES_IN_PROMPT = int(_self_cfg.get("episodes_in_prompt", 2))
SELF_IDLE_MINUTES = int(_self_cfg.get("idle_minutes", 30))
SELF_TIDY_FACTS = bool(_self_cfg.get("tidy_facts", True))
SELF_CALIBRATION = bool(_self_cfg.get("calibration", True))
SELF_HEDGE_BELOW = float(_self_cfg.get("hedge_below", 0.6))
SELF_HEDGE_LINE = str(_self_cfg.get("hedge_line",
                                    "I'm not totally sure about that one, though."))
SELF_GREET = bool(_self_cfg.get("greet", True))
# Recipes for multi-step jobs she's done well (mind/skills.py).
SELF_SKILLS = bool(_self_cfg.get("skills", True))
SELF_SKILLS_IN_PROMPT = int(_self_cfg.get("skills_in_prompt", 2))
SELF_MAX_SKILLS = int(_self_cfg.get("max_skills", 60))
# Ongoing projects (mind/projects.py): work that spans sessions.
SELF_PROJECTS = bool(_self_cfg.get("projects", True))
SELF_PROJECTS_IN_PROMPT = int(_self_cfg.get("projects_in_prompt", 3))
# Pages (mind/pages.py): a short joined-up note per subject she knows a lot about.
SELF_PAGES = bool(_self_cfg.get("pages", True))
SELF_PAGES_IN_PROMPT = int(_self_cfg.get("pages_in_prompt", 2))

# The situation block (mind/situation.py): focused window, music, machine load,
# running plugins, next reminder, what's in her hands - a few live lines in
# every private turn.
_situation_cfg = setting("situation", {})
SITUATION_ENABLED = bool(_situation_cfg.get("enabled", True))
SITUATION_PARTS = {k: bool(_situation_cfg.get(k, True))
                   for k in ("window", "music", "machine", "plugins", "reminders", "hands", "clothes")}


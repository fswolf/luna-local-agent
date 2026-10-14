"""The conversation engine: prompts in, a spoken answer out.

It used to be one 2,400-line llm.py. Same code, split by job:

    session      switches that last the session (are tools working?)
    prompts      the system prompt and generation parameters
    replay       stored history turned back into messages
    streaming    one completion from the model server, streamed
    rounds       the tool loop
    second_look  adaptive thinking, rethink, vote, calibration, grounding
    turns        ask(): one turn end to end; prompt_budget() for /context

Everything other modules use is re-exported here, so `import llm` and
`llm.ask(...)` work exactly as before.
"""
from .session import tools_active
from .prompts import (build_generation_params, build_memory_prompt, build_self_prompt,
                      build_system_prompt, build_tools_prompt)
from .replay import _demonstration, _has_tool_example, _replay, _timing_note
from .streaming import _last_raw, _note_tokens
from .rounds import _tool_rounds
from .second_look import _rethink
from .turns import _record_thoughts, ask, prompt_budget

__all__ = [
    "ask", "prompt_budget", "tools_active",
    "build_system_prompt", "build_memory_prompt", "build_self_prompt", "build_tools_prompt",
    "build_generation_params",
    # Internals other modules reach for (introspection, diagnose, reflect,
    # the Discord and job paths). Listed so it's clear they're on purpose.
    "_demonstration", "_has_tool_example", "_replay", "_timing_note", "_last_raw",
    "_note_tokens", "_tool_rounds", "_rethink", "_record_thoughts",
]

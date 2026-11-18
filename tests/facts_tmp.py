"""A throwaway facts.db for a test: mind/factstore.py and mind/longterm.py
pointed at a file in a temp folder, the old-memory.json import reset.

    from tests.facts_tmp import use_temp_facts
    use_temp_facts(self, folder)                    # in setUp
    use_temp_facts(self, folder, old=["a fact"])    # an old memory.json's facts
"""
import os
from unittest import mock


def use_temp_facts(test, folder, old=None):
    from mind import factstore, forgetting, longterm

    # A forget sweeps every other store (mind/forgetting.py): never the real
    # ones from a test. test.swept collects what it was asked to take out.
    test.swept = []
    patches = [
        mock.patch.object(forgetting, "scrub_everywhere", lambda tombs: test.swept.append(tombs) or {}),
        mock.patch.object(forgetting, "_drop_vectors", lambda texts: None),
        mock.patch.object(factstore, "DB_FILE", os.path.join(folder, "facts.db")),
        mock.patch.object(factstore, "_db", None),
        mock.patch.object(factstore, "_unavailable", None),
        mock.patch.object(factstore, "_fts", True),
        mock.patch.object(longterm, "_imported", [False]),
        mock.patch.dict(longterm.memory, {"long_term_facts": list(old or [])}, clear=True),
    ]
    for p in patches:
        p.start()

    def close():
        if factstore._db is not None:
            factstore._db.close()
        for p in reversed(patches):
            p.stop()

    test.addCleanup(close)

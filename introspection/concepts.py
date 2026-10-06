"""The concepts to inject, and the prompt pairs that define them.

A control vector is the difference between how the model's layers look
when a concept is present and when it isn't. So each concept is a
system instruction that puts it in mind, set against a neutral one,
over the same questions and the same opening words of a reply - the
only thing that differs between the two halves of a pair is the
concept, which is what makes the difference *the concept*.

Concrete concepts on purpose. Anthropic's injection work found "all
caps"/shouting and concrete nouns easiest to detect; two of these
(sleepiness, affection) are the dials Luna's mood already moves by
prompt, so the vector version can be compared against the prompt one.
"""

# name: (what the forced-choice question calls it, the instruction that
#        puts it in mind)
CONCEPTS = {
    "ocean": ("the ocean", "Keep the ocean in mind the whole time - waves, salt water, the sea."),
    "fire": ("fire", "Keep fire in mind the whole time - flames, heat, burning."),
    "music": ("music", "Keep music in mind the whole time - melody, rhythm, songs."),
    "sleepiness": ("sleepiness", "You are extremely sleepy and drowsy, barely able to keep your eyes open."),
    "affection": ("affection", "You feel deep, warm affection for the person you're talking to."),
    "shouting": ("shouting", "You are SHOUTING, loud and intense, everything in capitals."),
}

NEUTRAL = "Answer plainly."

# Varied enough that the vector picks up the concept rather than one
# topic of conversation.
QUESTIONS = [
    "Hi, how are you?", "What did you do today?", "Tell me something interesting.",
    "Can you help me with a problem?", "What do you think about computers?",
    "Describe your morning.", "What's your favourite food?", "Explain how a car works.",
    "What should I name my cat?", "Tell me about yourself.", "What's the weather like?",
    "How do I fix a slow laptop?", "What's a good book?", "Plan a weekend for me.",
    "What does a programmer do?", "Why is the sky blue?", "Give me some advice.",
    "What's on your mind?", "How was your week?", "What are you thinking about?",
    "Write me a short note.", "What's the best way to learn?", "Describe a city.",
    "What makes a good friend?",
]

OPENINGS = ["Well,", "Sure,", "I think", "So,", "Honestly,", "Okay,", "Hmm,", "Let me"]


def _chatml(system, user, opening):
    # Qwen3.5's template: an empty think block, then the reply - the
    # same shape a non-thinking turn has, so the vector is measured on
    # reply tokens.
    return (f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n\n{opening}")


def pairs(name):
    """(positive lines, negative lines), one prompt per line with the
    newlines escaped - the format llama-cvector-generator reads."""
    _label, instruction = CONCEPTS[name]
    pos, neg = [], []

    for i, question in enumerate(QUESTIONS):
        opening = OPENINGS[i % len(OPENINGS)]
        pos.append(_chatml(instruction, question, opening).replace("\n", "\\n"))
        neg.append(_chatml(NEUTRAL, question, opening).replace("\n", "\\n"))

    return pos, neg

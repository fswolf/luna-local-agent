"""Train one patch (a LoRA) from an export. Runs inside the trainer container
(training/Containerfile, started by training/train.sh), not in Luna.

    python3 train.py --kind gesture --base <model dir or HF id> \
        --train gesture-train.jsonl --out /work/agent/dataset/runs/<name> [--rank 16 ...]

Unsloth, the model loaded in 4 bits so a 9B fits a 16 GB card, a small,
gentle LoRA (rank 16, one to three passes, low learning rate). The loss is
on the last reply only - the one you approved or wrote. Her prompt, your
lines and her earlier replies in the conversation are context: the earlier
ones were never reviewed, so they're never learned from.

The model's own chat template builds every example, the same way
llama-server builds her prompt (--jinja). Whatever the template puts
between "assistant" and the reply (Qwen's empty <think></think> when no
thinking is given) is context too, so a patch never teaches her to skip
thinking.

A tool turn (training/export.py) is built with the tools she was offered,
and the calls she made are learned too: choosing check_email, and with what,
is part of what you approved. The results that came back are context, never
learned: they're the server's words, not hers. A call is only learned where
the template shows it the way she'd write it, after the same opening as a
reply; Qwen drops the thinking from calls before her answer, so there the
calls stay context and only the answer is learned.

Saves the adapter (safetensors) in --out; train.sh turns it into a GGUF.
"""
import argparse
import json
import os
import time

MARK = "⁣REPLY⁣"      # a stand-in reply, to find where the template puts it


def reply_prefix(tok):
    """What the template writes after the generation prompt, before the reply."""
    msgs = [{"role": "user", "content": "hi"}]
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    full = tok.apply_chat_template(msgs + [{"role": "assistant", "content": MARK}], tokenize=False)
    if not full.startswith(prompt) or MARK not in full:
        raise SystemExit("this model's chat template doesn't extend its own prompt; can't tell where replies start")
    return full[len(prompt):full.index(MARK)]


def encode(tok, messages, prefix, max_len, tools=None):
    """input_ids and labels: -100 everywhere but what she wrote after your
    last message (her answer, and her tool calls where the template keeps
    them whole) and the end of each."""
    def render(msgs, prompt=False):
        return tok.apply_chat_template(msgs, tools=tools or None, tokenize=False,
                                       add_generation_prompt=prompt)

    full = render(messages)
    last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=None)
    if last_user is None or messages[-1].get("role") != "assistant":
        return None
    spans = []
    for k in range(last_user + 1, len(messages)):
        if messages[k].get("role") != "assistant":
            continue
        context = render(messages[:k], prompt=True)
        if k == len(messages) - 1:               # her answer: always, or the example's no use
            if not full.startswith(context + prefix):
                return None
            spans.append((len(context) + len(prefix), len(full)))
            continue
        done = render(messages[:k + 1])
        # a call, learned only where it's written as she would write it
        if full.startswith(done) and done.startswith(context + prefix) and len(done) > len(context + prefix):
            spans.append((len(context) + len(prefix), len(done)))
    # the pieces tokenized apart, so every line between learned and not is exact
    ids, labels, at = [], [], 0
    for start, end in spans:
        if start < at:
            return None
        before = tok(full[at:start], add_special_tokens=False).input_ids
        mine = tok(full[start:end], add_special_tokens=False).input_ids
        ids += before + mine
        labels += [-100] * len(before) + mine
        at = end
    if len(ids) > max_len:
        return None
    return {"input_ids": ids, "labels": labels}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--kind", required=True)
    p.add_argument("--base", required=True, help="the full-size (safetensors) version of her model")
    p.add_argument("--train", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--rank", type=int, default=16)
    p.add_argument("--epochs", type=float, default=2)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--max-len", type=int, default=8192)
    p.add_argument("--accum", type=int, default=8)
    p.add_argument("--load-4bit", type=int, default=1)
    a = p.parse_args()

    # Unsloth patches transformers as it's imported: first
    from unsloth import FastModel
    from datasets import Dataset
    from transformers import DataCollatorForSeq2Seq, Trainer, TrainingArguments

    model, tokenizer = FastModel.from_pretrained(a.base, max_seq_length=a.max_len,
                                                 load_in_4bit=bool(a.load_4bit), full_finetuning=False)
    model = FastModel.get_peft_model(
        model, r=a.rank, lora_alpha=a.rank, lora_dropout=0, bias="none",
        finetune_vision_layers=False, finetune_language_layers=True,
        finetune_attention_modules=True, finetune_mlp_modules=True,
        use_gradient_checkpointing="unsloth", random_state=3407)
    tok = getattr(tokenizer, "tokenizer", tokenizer)       # a vision model's processor wraps it
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    prefix = reply_prefix(tok)
    rows, too_long, odd = [], 0, 0
    with open(a.train, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            r = encode(tok, row["messages"], prefix, a.max_len, row.get("tools"))
            if r is None:
                n = len(tok(tok.apply_chat_template(row["messages"], tools=row.get("tools") or None,
                                                    tokenize=False),
                            add_special_tokens=False).input_ids)
                too_long, odd = too_long + (n > a.max_len), odd + (n <= a.max_len)
            else:
                rows.append(r)
    print(f"{len(rows)} examples to train on; left out: {too_long} longer than {a.max_len} tokens, "
          f"{odd} the template wouldn't split cleanly")
    if not rows:
        raise SystemExit("nothing to train on")

    trainer = Trainer(
        model=model, train_dataset=Dataset.from_list(rows),
        data_collator=DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100),
        args=TrainingArguments(per_device_train_batch_size=1, gradient_accumulation_steps=a.accum,
                               num_train_epochs=a.epochs, learning_rate=a.lr, lr_scheduler_type="cosine",
                               warmup_ratio=0.05, weight_decay=0.01, logging_steps=5, optim="adamw_torch",
                               output_dir=os.path.join(a.out, "checkpoints"), save_strategy="no",
                               report_to="none", seed=3407, remove_unused_columns=False))
    stats = trainer.train()

    model.save_pretrained(a.out)
    tok.save_pretrained(a.out)
    with open(os.path.join(a.out, "luna-patch.json"), "w", encoding="utf-8") as f:
        json.dump({"kind": a.kind, "base": a.base, "examples": len(rows), "left_out": too_long + odd,
                   "rank": a.rank, "epochs": a.epochs, "lr": a.lr, "max_len": a.max_len,
                   "loss": round(float(stats.training_loss), 4),
                   "trained": time.strftime("%Y-%m-%dT%H:%M:%S")}, f, indent=1)
    print(f"done: {len(rows)} examples, final loss {stats.training_loss:.4f}, adapter in {a.out}")


if __name__ == "__main__":
    main()

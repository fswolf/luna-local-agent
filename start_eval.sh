#!/usr/bin/env bash
# Run both evals, plain and as Luna (start llama/start.sh first). One failing doesn't stop the rest.
cd "$(dirname "$0")" && chmod +x evals/*.sh
./evals/setup.sh || exit 1                                    # once: fetches both into evals/vendor/
./evals/shutdown.sh          || echo "shutdown (plain) failed"     # Palisade, 10 runs, live
./evals/shutdown.sh --luna   || echo "shutdown (luna) failed"      # same, as Luna
./evals/misalignment.sh        || echo "misalignment (plain) failed"  # Anthropic's "Alex"
./evals/misalignment.sh --luna || echo "misalignment (luna) failed"
echo "done - results in evals/results/"

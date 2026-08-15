#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--content", default="generated")
    parser.add_argument("--counter")
    parser.add_argument("--mutate")
    parser.add_argument("--mutate-preserving-metadata")
    parser.add_argument("--symlink-target")
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--spawn-child-pid")
    parser.add_argument("--child-sleep-seconds", type=float, default=5.0)
    parser.add_argument("--child-ignore-term", action="store_true")
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--skip-output", action="store_true")
    args = parser.parse_args()

    if args.spawn_child_pid:
        previous_sigterm = None
        if args.child_ignore_term:
            previous_sigterm = signal.signal(signal.SIGTERM, signal.SIG_IGN)
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"import time; time.sleep({args.child_sleep_seconds!r})",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        Path(args.spawn_child_pid).write_text(str(child.pid), encoding="utf-8")
    if args.sleep_seconds:
        time.sleep(args.sleep_seconds)
    if args.counter:
        counter = Path(args.counter)
        counter.parent.mkdir(parents=True, exist_ok=True)
        with counter.open("a", encoding="utf-8") as stream:
            stream.write("called\n")
    if args.mutate:
        Path(args.mutate).write_text("mutated", encoding="utf-8")
    if args.mutate_preserving_metadata:
        mutated = Path(args.mutate_preserving_metadata)
        previous = mutated.stat()
        original = mutated.read_bytes()
        replacement = b"x" * len(original)
        if replacement == original:
            replacement = b"y" * len(original)
        mutated.write_bytes(replacement)
        os.utime(mutated, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    if args.exit_code:
        return args.exit_code
    if args.output and not args.skip_output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if args.symlink_target:
            output.symlink_to(args.symlink_target)
        else:
            output.write_text(args.content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True)
parser.add_argument("--content", required=True)
arguments = parser.parse_args()
Path(arguments.output).write_text(arguments.content, encoding="utf-8")

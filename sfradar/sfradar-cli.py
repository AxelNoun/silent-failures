#!/usr/bin/env python3
"""Thin launcher so the package runs without installation: python sfradar-cli.py TARGET [--out ...]"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from sfradar.scan import main
sys.exit(main())

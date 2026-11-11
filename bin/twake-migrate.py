#!/usr/bin/env python3
"""Source checkout entry point; installed users can run twake-migrate."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from twake_migrate.cli import main
raise SystemExit(main())

#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from twake_migrate.config.dependencies import fetch_design_dependencies
parser=argparse.ArgumentParser(description='Fetch lock-pinned Twake source packages with SHA-512 verification; no npm or install scripts')
parser.add_argument('--web',required=True)
parser.add_argument('--out',required=True)
args=parser.parse_args()
print(json.dumps(fetch_design_dependencies(args.web,args.out),indent=2))

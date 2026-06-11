import os
import sys

os.environ.setdefault("CADWRIGHT_LLM", "mock")   # deterministic offline tests
sys.path.insert(0, os.path.dirname(__file__))

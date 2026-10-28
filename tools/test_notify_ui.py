"""Run the actual notification controller regressions using Node, no device."""
from pathlib import Path
import subprocess
subprocess.run(['node',str(Path(__file__).with_suffix('.cjs'))],check=True,timeout=30)

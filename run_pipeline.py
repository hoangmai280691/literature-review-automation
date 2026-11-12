
from pathlib import Path
import subprocess
import os
import sys

ROOT = Path(__file__).resolve().parent

STEPS = [
    ("Deduplication", "de-dup", "notebook_dedup.py"),
    ("VHB reference", "VHB_reference", "vhb_reference_master.py"),
    ("VHB screening", "VHB", "notebook_vhb.py"),
]

for name, folder, filename in STEPS:
    working_dir = ROOT / folder
    script = working_dir / filename

    if not script.is_file():
        sys.exit(f"File not found: {script}")

    print(f"\n=== Running: {name} ===", flush=True)

    result = subprocess.run(
    [sys.executable, str(script)],
    cwd=working_dir,
    env=os.environ.copy(),
    )

    if result.returncode != 0:
        sys.exit(f"Stopped at: {name}")

    print(f"Completed: {name}", flush=True)

print("\nAll 3 steps completed!")
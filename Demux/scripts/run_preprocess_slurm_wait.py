#!/usr/bin/env python3
"""
Run PreProcess-SLURM.sh with -r runfolder, capture submitted SLURM job IDs,
then wait until all those jobs have completed. Exits 0 on success.
"""
import os
import re
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PREPROCESS_SLURM = os.path.join(SCRIPT_DIR, "PreProcess-SLURM.sh")


def main():
    argv = sys.argv[1:]
    partition = "solexa"
    if "--partition" in argv:
        i = argv.index("--partition")
        if i + 1 < len(argv):
            partition = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
    else:
        for a in argv:
            if a.startswith("--partition="):
                partition = a.split("=", 1)[1]
                argv = [x for x in argv if x != a]
                break

    if len(argv) < 1:
        print("Usage: run_preprocess_slurm_wait.py [--partition PARTITION] <runfolder>", file=sys.stderr)
        print("  --partition: SLURM partition (default: solexa)", file=sys.stderr)
        sys.exit(1)
    runfolder = argv[0]

    cmd = ["bash", PREPROCESS_SLURM, "-r", runfolder, "-p", partition]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    # sbatch prints "Submitted batch job N" to stdout
    job_ids = re.findall(r"Submitted batch job (\d+)", proc.stdout or "")
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        sys.exit(proc.returncode)

    if not job_ids:
        sys.exit(0)

    ids_str = ",".join(job_ids)
    print(f"Waiting for {len(job_ids)} PreProcess SLURM job(s)...")
    while True:
        result = subprocess.run(
            ["squeue", "-j", ids_str, "-h"],
            capture_output=True,
            text=True,
        )
        if not result.stdout.strip():
            break
        time.sleep(30)
    print("PreProcess SLURM jobs completed.")


if __name__ == "__main__":
    main()

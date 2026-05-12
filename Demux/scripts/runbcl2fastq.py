#!/usr/bin/env python3
"""
Submit SLURM jobs to demux Illumina (NovaSeq/MiSeq) or AVITI run folders.
NovaSeq/MiSeq: bcl2fastq, one job per lane.
AVITI: bases2fastq, single job (runfolder name must contain _AV240904_).
Use --wait to block until all submitted jobs have finished.
"""
import re
import subprocess
import sys
import os
import time

from runfolder_resolve import _sequencer_type

SLURM_OUTPUT_DIR = "/lab/htdata/SLURM"
SBATCH_IO = f"--output {SLURM_OUTPUT_DIR}/%j.out --error {SLURM_OUTPUT_DIR}/%j.err"


def _submit_and_capture_job_id(command):
    """Run sbatch command; return (job_id, None) or (None, stderr) on failure."""
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        return None, result.stderr or result.stdout
    # sbatch prints "Submitted batch job 12345" to stdout
    match = re.search(r"Submitted batch job (\d+)", result.stdout)
    return (match.group(1), None) if match else (None, "No job ID in output")


def _wait_for_job_ids(job_ids):
    """Poll squeue until none of the given job IDs are in the queue."""
    if not job_ids:
        return
    ids_str = ",".join(job_ids)
    while True:
        result = subprocess.run(
            ["squeue", "-j", ids_str, "-h"],
            capture_output=True,
            text=True,
        )
        if not result.stdout.strip():
            break
        time.sleep(30)


def run_novaseq(runfolder_dir, lanes, wait=False, partition="solexa"):
    """Submit one bcl2fastq job per lane (NovaSeq). Return list of job IDs."""
    runfolder_dir = os.path.abspath(runfolder_dir)
    sample_sheet = os.path.join(runfolder_dir, "samplesheet.csv")
    base_command = (
        f"sbatch --mem=64gb --cpus-per-task=20 --partition={partition} {SBATCH_IO} "
        '--wrap "bcl2fastq --runfolder-dir={runfolder_dir} '
        '--output-dir={runfolder_dir} '
        '--sample-sheet={sample_sheet} '
        '--tiles s_{lane} '
        '--reports-dir={runfolder_dir}/Lane{lane}Reports/ '
        '--stats-dir={runfolder_dir}/Lane{lane}Stats/ '
        '--loading-threads=20 --processing-threads=20 --writing-threads=20"'
    )
    job_ids = []
    for lane in lanes:
        command = base_command.format(
            runfolder_dir=runfolder_dir, lane=lane, sample_sheet=sample_sheet
        )
        print(f"Executing: {command}")
        jid, err = _submit_and_capture_job_id(command)
        if err is not None:
            print(f"Error for lane {lane}: {err}", file=sys.stderr)
            sys.exit(1)
        job_ids.append(jid)
    if wait and job_ids:
        print("Waiting for demux jobs to complete...")
        _wait_for_job_ids(job_ids)
    return job_ids


def run_aviti(runfolder_dir, wait=False, partition="solexa"):
    """Submit one bases2fastq job (AVITI). Return list of job IDs."""
    fastq_dir = os.path.join(runfolder_dir, "FASTQ")
    command = (
        f"sbatch --mem=200gb --cpus-per-task=20 --partition={partition} {SBATCH_IO} "
        f'--wrap "bases2fastq --split-lanes --legacy-fastq {runfolder_dir} {fastq_dir}/ --num-threads 20"'
    )
    print(f"Executing: {command}")
    jid, err = _submit_and_capture_job_id(command)
    if err is not None:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)
    job_ids = [jid] if jid else []
    if wait and job_ids:
        print("Waiting for demux job to complete...")
        _wait_for_job_ids(job_ids)
    return job_ids


DEFAULT_NOVASEQ_LANES = ("1", "2", "3", "4")


def main():
    raw = sys.argv[1:]
    wait = "--wait" in raw
    args = [a for a in raw if a != "--wait"]

    partition = "solexa"
    if "--partition" in args:
        i = args.index("--partition")
        if i + 1 < len(args):
            partition = args[i + 1]
            args = args[:i] + args[i + 2:]
    else:
        for a in args:
            if a.startswith("--partition="):
                partition = a.split("=", 1)[1]
                args = [x for x in args if x != a]
                break

    if len(args) < 1:
        print("Usage: runbcl2fastq.py [--wait] [--partition PARTITION] <runfolder_dir> [lane1 lane2 ...]")
        print("  --wait: wait until all submitted SLURM jobs finish before exiting")
        print("  --partition: SLURM partition (default: solexa)")
        print("  NovaSeq/MiSeq (_A01100_/_SH01116_): one bcl2fastq job per lane; defaults to lanes 1 2 3 4 if not given.")
        print("  AVITI (_AV240904_): single bases2fastq job; no lane args.")
        sys.exit(1)

    runfolder_dir = os.path.abspath(args[0])
    if not os.path.isdir(runfolder_dir):
        print(f"Error: Run folder directory {runfolder_dir} does not exist.")
        sys.exit(1)

    seq_type = _sequencer_type(runfolder_dir)
    if seq_type == "aviti":
        run_aviti(runfolder_dir, wait=wait, partition=partition)
    elif seq_type in ("novaseq", "miseq"):
        lanes = args[1:] if len(args) > 1 else list(DEFAULT_NOVASEQ_LANES)
        run_novaseq(runfolder_dir, lanes, wait=wait, partition=partition)
    else:
        print(
            "Error: Sequencer not supported. Run folder name must contain _A01100_ (NovaSeq), _SH01116_ (MiSeq), or _AV240904_ (AVITI).",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

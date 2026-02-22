# Demux

Snakemake workflow for demultiplexing Illumina (NovaSeq) and AVITI sequencing run folders. The pipeline runs demux (bcl2fastq or bases2fastq), optional AVITI FASTQ flattening, PreProcess (fastqc/fastq_screen via SLURM), summary, QC info, and email notification.

## Requirements

- **Snakemake** (run with `--cores 1`; actual compute runs in SLURM)
- **Python 3** (for scripts in `scripts/`)
- **SLURM** (sbatch, squeue) for job submission
- Access to runfolder paths and any cluster paths used by the scripts (e.g. `/lab/htdata/SLURM`)

## Usage

You can run the workflow from any directory. Point Snakemake at the Snakefile with `-s` and pass the runfolder (absolute path recommended when not in `Demux/`):

```bash
# From the Demux directory
snakemake all -s Snakefile --cores 1 --config runfolder=/path/to/runfolder

# From elsewhere (use path to Snakefile and absolute runfolder)
snakemake all -s /path/to/Demux/Snakefile --cores 1 --config runfolder=/lab/htdata/AV240904/your_runfolder
```

Optional SLURM partition (default: `solexa`):

```bash
snakemake all -s Snakefile --cores 1 --config runfolder=/path/to/runfolder partition=solexa
```

Paths to scripts and workflow files are resolved from the Snakefile’s location, not the current working directory. Use an absolute `runfolder` when running from an arbitrary directory to avoid confusion.

## Config

| Option      | Required | Default   | Description                    |
|------------|----------|-----------|--------------------------------|
| `runfolder`| yes      | —         | Absolute or relative path to runfolder |
| `partition`| no       | `solexa`  | SLURM `--partition` for jobs   |

## Pipeline steps

1. **demux** – Submits SLURM jobs (runbcl2fastq / bases2fastq) and waits for completion.
2. **aviti_flatten_fastq** – If runfolder is AVITI, moves `*fastq.gz` from subdirs into `FASTQ/`.
3. **preprocess_slurm** – Runs PreProcess-SLURM (fastqc, fastq_screen) and waits.
4. **preprocess_summary** – PreProcess-Summary.
5. **getQCinfo** – getQCinfo_by_runfolder.
6. **email** – Sends completion email.

Files (e.g. `.snakemake_demux.done`) are written inside the runfolder to track completion.

## Scripts

| Script | Purpose |
|--------|---------|
| `runbcl2fastq.py` | Submit SLURM demux jobs (bcl2fastq for NovaSeq, bases2fastq for AVITI); supports `--wait`. |
| `runfolder_resolve.py` | Resolve runfolder path and sequencer type (e.g. AVITI). |
| `run_preprocess_slurm_wait.py` | Run PreProcess-SLURM and wait for jobs. |
| `PreProcess-SLURM.sh` | Submit fastqc/fastq_screen SLURM jobs. |
| `PreProcess-Summary.sh` | Generate PreProcess summary. |
| `getQCinfo_by_runfolder.py` | Extract QC info by runfolder. |
| `update_runinfo_consumables.py` | Update runinfo consumables. |
| `Make_Delivery_Package.py` | Build delivery package. |

## License

Internal / lab use.

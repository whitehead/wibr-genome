#!/usr/bin/env python3
"""
Collect QC info by run folder and optionally update SAMPLERUNINFO in the database.
Reads Bowtie_Result_Extended, FASTQC multiqc, and FASTQSCREEN multiqc outputs.
Credentials from config file or GTC_DB_* environment variables (never hardcoded).

If runfolder is not specified, it is derived from localdir via runfolder_resolve (NovaSeq/AVITI rules).
"""
import os
import re
import sys
import glob
import subprocess
from db_config import get_connection, load_config
from runfolder_resolve import resolve_runfolder


def get_run_index(cursor, runfolder):
    """Return RUNINDEX for the given runfolder, or None if not found."""
    cursor.execute(
        "SELECT RUNINDEX FROM RUNINFO WHERE RUNFOLDER = %s",
        (runfolder,),
    )
    row = cursor.fetchone()
    return row["RUNINDEX"] if row else None


def read_file_to_2d_array(filepath):
    """Read a tab-separated file into a list of rows (each row is a list of fields)."""
    out = []
    with open(filepath) as f:
        for line in f:
            out.append(line.rstrip("\n\r").split("\t"))
    return out


def load_aligned_data(aligned_dir):
    """
    Parse Bowtie_Result_Extended directory: .aligned, .unaligned, .rip,
    .totalpeaks, and .cov (for complexreads). Return nested dict
    aligned_data[metric][barcode][lane] = value.
    """
    aligned_data = {}
    if not aligned_dir or not os.path.isdir(aligned_dir):
        return aligned_data

    for fname in os.listdir(aligned_dir):
        if "-" not in fname:
            continue
        parts = fname.split("-")
        name_part = parts[1]
        lane_part = re.sub(r"L00", "", name_part.split("_")[3]) if "_" in name_part else name_part
        barcode = parts[0]
        filepath = os.path.join(aligned_dir, fname)

        if fname.endswith(".aligned"):
            with open(filepath) as f:
                aligned_data.setdefault("aligned", {}).setdefault(barcode, {})[lane_part] = f.read().strip()
        elif fname.endswith(".unaligned"):
            with open(filepath) as f:
                aligned_data.setdefault("unaligned", {}).setdefault(barcode, {})[lane_part] = f.read().strip()
        elif fname.endswith(".rip"):
            with open(filepath) as f:
                aligned_data.setdefault("rip", {}).setdefault(barcode, {})[lane_part] = f.read().strip()
        elif fname.endswith(".totalpeaks"):
            with open(filepath) as f:
                aligned_data.setdefault("numbofpeaks", {}).setdefault(barcode, {})[lane_part] = f.read().strip()
        elif fname.endswith(".cov"):
            aligned_data.setdefault("complexreads", {}).setdefault(barcode, {})[lane_part] = 0
            with open(filepath) as f:
                for line in f:
                    if not line.startswith("genome"):
                        continue
                    fields = line.split("\t")
                    if len(fields) >= 3:
                        try:
                            aligned_data["complexreads"][barcode][lane_part] += int(fields[2])
                        except (ValueError, IndexError):
                            pass

    return aligned_data


def load_multiqc_general_stats(multiqc_file, aligned_data, key_totalreads=None, key_gc=None, key_dup=None):
    """Parse multiqc_general_stats.txt and fill aligned_data totalreads/gcpercent/duppercent."""
    if not multiqc_file or not os.path.isfile(multiqc_file):
        return
    rows = read_file_to_2d_array(multiqc_file)
    for row in rows:
        if not row:
            continue
        lineannotation = row[0].split("_")
        if len(lineannotation) < 4:
            continue
        barcode = f"{lineannotation[0]}_{lineannotation[1]}"
        lane = re.sub(r"L00", "", lineannotation[3])
        if key_gc is not None and len(row) > 2:
            aligned_data.setdefault("gcpercent", {}).setdefault(barcode, {})[lane] = row[2]
        if key_dup is not None and len(row) > 1:
            aligned_data.setdefault("duppercent", {}).setdefault(barcode, {})[lane] = row[1]
        if key_totalreads is not None and len(row) > 6:
            aligned_data.setdefault("totalreads", {}).setdefault(barcode, {})[lane] = row[6]


def load_fastqc_multiqc(fastqmultiqc_file, aligned_data):
    """Parse multiqc_fastqc.txt for totalreads (column index 4)."""
    if not fastqmultiqc_file or not os.path.isfile(fastqmultiqc_file):
        return
    rows = read_file_to_2d_array(fastqmultiqc_file)
    for row in rows:
        if not row or len(row) < 5:
            continue
        lineannotation = row[0].split("_")
        if len(lineannotation) < 4:
            continue
        barcode = f"{lineannotation[0]}_{lineannotation[1]}"
        lane = re.sub(r"L00", "", lineannotation[3])
        aligned_data.setdefault("totalreads", {}).setdefault(barcode, {})[lane] = row[4]


def load_fastqscreen_stats(fastscreenqc_file, aligned_data):
    """Parse FASTQSCREEN multiqc_general_stats for species percentages."""
    if not fastscreenqc_file or not os.path.isfile(fastscreenqc_file):
        return
    rows = read_file_to_2d_array(fastscreenqc_file)
    keys = [
        "humanpercent", "mouseppercent", "hgribopercent", "arabippercent",
        "flypercent", "fishpercent", "yeastpercent", "phixpercent", "ecolipercent", "adappercent",
    ]
    for row in rows:
        if not row or len(row) < 21:
            continue
        lineannotation = row[0].split("_")
        if len(lineannotation) < 4:
            continue
        barcode = f"{lineannotation[1]}_{lineannotation[1]}"
        lane = re.sub(r"L00", "", lineannotation[3])
        for i, key in enumerate(keys):
            idx = 2 + i * 2
            if idx < len(row):
                aligned_data.setdefault(key, {}).setdefault(barcode, {})[lane] = row[idx]


def run_multiqc(directory, datatype):
    """Run multiqc on directory and per-lane reports (FASTQC / FASTQSCREEN)."""
    subprocess.run(["multiqc", "--force", directory, "--outdir", directory], check=False)
    for i in range(1, 9):
        pattern = f"{directory}/*_*_L00{i}_*"
        subprocess.run([
            "multiqc", "--force", "--outdir", directory,
            "--filename", f"{datatype}_MULTIQC_L{i}_Interactive", pattern,
        ], check=False)
        subprocess.run([
            "multiqc", "--force", "--outdir", directory, "--template", "simple",
            "--filename", f"{datatype}_MULTIQC_L{i}_Simple", pattern,
        ], check=False)


def get_metric(aligned_data, metric, barcode, lane, default=0):
    """Safe read from aligned_data[metric][barcode][lane], with optional default."""
    try:
        return aligned_data.get(metric, {}).get(barcode, {}).get(lane, default)
    except (TypeError, AttributeError):
        return default


def process_fastq_and_update_db(localdir, runindex, aligned_data, run_mode, conn):
    """
    Iterate over FASTQ R1 files in localdir/FASTQ, build UPDATE for each lane/barcode,
    print and optionally execute when run_mode==1.
    """
    fastq_dir = os.path.join(localdir, "FASTQ")
    if not os.path.isdir(fastq_dir):
        return

    query_update = (
        "UPDATE SAMPLERUNINFO "
        "LEFT JOIN RUNINFO ON SAMPLERUNINFO.RUNINDEX = RUNINFO.RUNINDEX "
        "LEFT JOIN SUBMISSIONHISTORY ON SAMPLERUNINFO.pendindex = SUBMISSIONHISTORY.pendindex"
    )

    for filepath in glob.glob(os.path.join(fastq_dir, "*.*")):
        if "_001.fastq.gz" not in filepath and "_R1.fastq.gz" not in filepath:
            continue

        fname = os.path.basename(filepath)
        parts = fname.replace("\n", "").replace("\r", "").split("_")
        if len(parts) < 4:
            continue

        lane = re.sub(r"L00", "", parts[3])
        barcode = f"{parts[0]}_{parts[1]}"
        if barcode == "s":
            barcode = "N"

        aligned = float(get_metric(aligned_data, "aligned", barcode, lane, 0))
        unaligned = float(get_metric(aligned_data, "unaligned", barcode, lane, 0))
        complexreads = float(get_metric(aligned_data, "complexreads", barcode, lane, 0))
        rip = float(get_metric(aligned_data, "rip", barcode, lane, 0))
        numbofpeaks = float(get_metric(aligned_data, "numbofpeaks", barcode, lane, 0))
        gcpercent = float(get_metric(aligned_data, "gcpercent", barcode, lane, 0))
        duppercent = float(get_metric(aligned_data, "duppercent", barcode, lane, 0))
        totalreads = float(get_metric(aligned_data, "totalreads", barcode, lane, 0))

        queryset = (
            "alignedreads=%s, unalignedreads=%s, uniquealignedreads=%s, "
            "numbofpeaks=%s, readsinpeaks=%s, gcpercent=%s, totalreads=%s, duppercent=%s"
        )
        querywhere = "WHERE RUNINFO.RUNINDEX=%s AND SAMPLERUNINFO.LANE=%s"
        params = [
            f"{aligned:.2f}", f"{unaligned:.2f}", f"{complexreads:.2f}",
            f"{numbofpeaks:.2f}", f"{rip:.2f}", f"{gcpercent:.2f}",
            f"{totalreads:.2f}", f"{duppercent:.2f}",
            runindex, lane,
        ]
        if barcode != "N":
            querywhere += " AND SUBMISSIONHISTORY.GTCID = %s"
            params.append(barcode)

        full_sql = f"{query_update} SET {queryset} {querywhere}"
        print(f"{lane}\t{barcode}\t{totalreads:.2f}\t{aligned:.2f}\t{unaligned:.2f}\t{complexreads:.2f}\t{rip:.2f}\t{numbofpeaks:.2f}\t{gcpercent:.2f}\t{duppercent:.2f}")

        if run_mode == 1:
            with conn.cursor() as cur:
                cur.execute(
                    f"{query_update} SET {queryset} {querywhere}",
                    params,
                )
                if cur.rowcount == 0:
                    print("No data updated.\n")
                conn.commit()


def main():
    if len(sys.argv) < 3:
        print("Usage: getQCinfo_by_runfolder.py <localdir> <run> [runfolder]")
        print("  localdir  = directory with FASTQ, Bowtie_Result_Extended, FASTQC (must be a folder)")
        print("  run       = 0 for dry run, 1 to perform DB updates")
        print("  runfolder = optional; RUNFOLDER for RUNINFO. If omitted, derived from localdir via RunParameters.xml <side>")
        sys.exit(1)

    localdir = os.path.abspath(sys.argv[1])
    if not os.path.isdir(localdir):
        print(f"Error: localdir is not a directory: {localdir}", file=sys.stderr)
        sys.exit(1)

    run_mode = int(sys.argv[2])
    runfolder_arg = sys.argv[3] if len(sys.argv) > 3 else None

    runfolder = resolve_runfolder(localdir, runfolder_arg)
    print(f"Using runfolder: {runfolder}")

    conn = get_connection()
    runindex = None
    try:
        with conn.cursor() as cursor:
            runindex = get_run_index(cursor, runfolder)
            if runindex is None:
                print("Run folder not found in database. Exiting without processing.")
            else:
                print(f"Run folder found in database (RUNINDEX={runindex}).")
    finally:
        conn.close()

    if runindex is None:
        return

    print("LANE\tBARCODE\tTotalReads\tAligned\tUnaligned\tComplexReads\tRiP\tNumPeaks\tGC%\tDup%")

    aligned_dir = os.path.join(localdir, "Bowtie_Result_Extended")
    fastqcdir = os.path.join(localdir, "FASTQC")
    fastqscreen_dir = os.path.join(localdir, "FASTQSCREEN")

    multiqcfile = os.path.join(localdir, "FASTQC", "multiqc_data", "multiqc_general_stats.txt")
    fastscreenqcfile = os.path.join(localdir, "FASTQSCREEN", "multiqc_data", "multiqc_general_stats.txt")
    fastqmultiqcfile = os.path.join(localdir, "FASTQC", "multiqc_data", "multiqc_fastqc.txt")

    aligned_data = load_aligned_data(aligned_dir)
    load_multiqc_general_stats(multiqcfile, aligned_data, key_totalreads=6, key_gc=2, key_dup=1)
    load_fastqc_multiqc(fastqmultiqcfile, aligned_data)
    load_fastqscreen_stats(fastscreenqcfile, aligned_data)

    conn = get_connection()
    process_fastq_and_update_db(localdir, runindex, aligned_data, run_mode, conn)
    conn.close()


if __name__ == "__main__":
    main()

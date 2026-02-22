#!/usr/bin/env python3
"""
Create delivery packages per lab: create dirs, lane annotation XLS, and copy
FASTQ/FASTQC/PrepFragmentSizes/FASTQSCREEN/MULTIQC via sbatch.
Uses config file or GTC_DB_* environment variables for DB credentials (never hardcoded).

htdatafolder is the data directory (same as localdir in getQCinfo_by_runfolder.py).
runfolder can be omitted and is then derived from htdatafolder via runfolder_resolve
(NovaSeq _A01100_ / AVITI _AV240904_ and RunParameters.xml or RunParameters.json).
"""
import os
import sys
from pathlib import Path

from db_config import get_connection
from runfolder_resolve import resolve_runfolder

# Set to 1 only by editing this file to print MySQL and sbatch commands (for debugging).
hardcodeddebug = 0

# Paths for FragmentAnalyzer and Bioanalyzer (optional)
FA_PROJECTS = "/nfs/WIGTC/Service_Projects/FragmentAnalyzer_Projects"
BIOA_PROJECTS = "/nfs/WIGTC/Service_Projects/Bioanalyzer_Projects"
DEFAULT_PARTITION = "solexa"
SLURM_OUTPUT_DIR = "/lab/htdata/SLURM"
SBATCH_IO = f"--output {SLURM_OUTPUT_DIR}/%j.out --error {SLURM_OUTPUT_DIR}/%j.err"

LANE_ANNOTATION_HEADER = (
    "Position\tSampleType\tOrganism\tGelPrepDate\tSampleName\tBarcode\t"
    "InsertSizeRange\tAverageFragmentSize\tID\tUserName\tGroup\tAdaptor\tSeqPrimer\tSeqType\t"
    "ReferenceGenome\tconcbyNanoDrop(ng/ul)(orig.)\tconcbyqPCR(nM)(DF)\tconcbyBioA(nM)(DF)\t"
    "concbyQubit(nM)(DF)\tConcUsed\tNANODROP BASED DF\tDF\tulindencktl\tulloaded\tpMloaded\t"
    "Equimolar?\tFlowCell\tSequencer\tQC\tTotal Reads\t% Q30\t% Pass Filer\t% Adapter\t"
    "% Aligned\t% Complexity\tNumberOfPeaks\t%RiP\tPrep - Input NanoDrop Conc.\t"
    "Prep - Input QBIT Conc.\tPrep - Conc. Used\tPrep - Input Amount Used\tPrep Method\t"
    "Prep - AO Input\tPrep - PCR Cycles\tPrep QC\n"
)


def get_run_index(cursor, runfolder):
    """Return RUNINDEX for runfolder, or None."""
    sql = "SELECT RUNINDEX FROM RUNINFO WHERE RUNFOLDER = %s"
    params = (runfolder,)
    if hardcodeddebug:
        print(sql, params)
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return row["RUNINDEX"] if row else None


def fetch_distinct_labids(cursor, runindex):
    """Return list of distinct LABID values for this runindex from gtc.exportfcruninfo."""
    sql = "SELECT DISTINCT LABID FROM gtc.exportfcruninfo WHERE RUNINDEX = %s ORDER BY LABID"
    if hardcodeddebug:
        print(sql, (runindex,))
    cursor.execute(sql, (runindex,))
    rows = cursor.fetchall()
    return [row["LABID"] for row in rows] if rows else []


def fetch_export_runinfo(cursor, runindex, labid):
    """Fetch rows from gtc.exportfcruninfo for the given runindex (and optional labid)."""
    if labid != "all":
        sql = (
            "SELECT * FROM gtc.exportfcruninfo WHERE RUNINDEX = %s AND LABID = %s "
            "ORDER BY LANE ASC, pendindex ASC"
        )
        params = (runindex, labid)
    else:
        sql = (
            "SELECT * FROM gtc.exportfcruninfo WHERE RUNINDEX = %s ORDER BY LANE ASC, pendindex ASC"
        )
        params = (runindex,)
    if hardcodeddebug:
        print(sql, params)
    cursor.execute(sql, params)
    return cursor.fetchall()


def ensure_delivery_dirs(base_path, runfolder):
    """Create runfolder and subdirs FASTQ, FASTQC, PrepFragmentSizes, FASTQSCREEN, MULTIQC."""
    subdirs = ["FASTQ", "FASTQC", "PrepFragmentSizes", "FASTQSCREEN", "MULTIQC"]
    for sub in subdirs:
        Path(base_path, runfolder, sub).mkdir(parents=True, exist_ok=True)


def sbatch_cp(src_glob, dest_dir, partition=DEFAULT_PARTITION):
    """Run sbatch to copy src_glob into dest_dir."""
    cmd = (
        f'sbatch --mem=1gb --cpus-per-task=1 --partition={partition} {SBATCH_IO} '
        f'--wrap "cp {src_glob} {dest_dir}/"'
    )
    if hardcodeddebug:
        print(cmd)
    os.system(cmd)


def sbatch_cp_force(src_glob, dest_dir, partition=DEFAULT_PARTITION):
    """Run sbatch to copy with -f into dest_dir."""
    cmd = (
        f'sbatch --mem=1gb --cpus-per-task=1 --partition={partition} {SBATCH_IO} '
        f'--wrap "cp -f {src_glob} {dest_dir}/"'
    )
    if hardcodeddebug:
        print(cmd)
    os.system(cmd)


def copyset(barcode, lane, htdatafolder, fapdf, bioapdf, runfolder_path, partition=DEFAULT_PARTITION):
    """
    Schedule copy jobs for one barcode/lane: FASTQ R1/R2, FASTQC R1/R2,
    FragmentAnalyzer/Bioanalyzer PDFs if present, FASTQSCREEN, MULTIQC.
    """
    b = barcode
    L = int(lane) if lane is not None else lane  # avoid L001.0 / L1.0 when lane is float from DB
    ht = htdatafolder
    rp = str(runfolder_path)

    fastq_r1 = f"{ht}/FASTQ/{b}_S*_L00{L}_R1*.fastq.gz"
    fastq_r2 = f"{ht}/FASTQ/{b}_S*_L00{L}_R2*.fastq.gz"
    fastqc_r1 = f"{ht}/FASTQC/{b}_S*_L00{L}_R1*_fastqc.html"
    fastqc_r2 = f"{ht}/FASTQC/{b}_S*_L00{L}_R2*_fastqc.html"
    screen_r2 = f"{ht}/FASTQSCREEN/{b}_S*_L00{L}_R2*"
    screen_r1 = f"{ht}/FASTQSCREEN/{b}_S*_L00{L}_R1_*"
    multiqc_fastqc = f"{ht}/MULTIQC/FASTQC_MULTIQC_L{L}*.html"
    multiqc_screen = f"{ht}/MULTIQC/FASTQSCREEN_MULTIQC_L{L}*.html"

    if hardcodeddebug:
        print(fastq_r1)
    sbatch_cp(fastq_r1, f"{rp}/FASTQ", partition)
    sbatch_cp(fastq_r2, f"{rp}/FASTQ", partition)
    sbatch_cp(fastqc_r1, f"{rp}/FASTQC", partition)
    sbatch_cp(fastqc_r2, f"{rp}/FASTQC", partition)

    if fapdf and fapdf != "NONE" and os.path.isfile(os.path.join(FA_PROJECTS, fapdf)):
        os.system(
            f'sbatch --mem=1gb --cpus-per-task=1 --partition={partition} {SBATCH_IO} '
            f'--wrap "cp {FA_PROJECTS}/{fapdf} {rp}/PrepFragmentSizes/FA-{fapdf}"'
        )
    if bioapdf and bioapdf != "NONE" and os.path.isfile(os.path.join(BIOA_PROJECTS, bioapdf)):
        os.system(
            f'sbatch --mem=1gb --cpus-per-task=1 --partition={partition} {SBATCH_IO} '
            f'--wrap "cp {BIOA_PROJECTS}/{bioapdf} {rp}/PrepFragmentSizes/BIOA-{bioapdf}"'
        )

    sbatch_cp(screen_r2, f"{rp}/FASTQSCREEN", partition)
    sbatch_cp(screen_r1, f"{rp}/FASTQSCREEN", partition)
    sbatch_cp_force(multiqc_fastqc, f"{rp}/MULTIQC", partition)
    sbatch_cp_force(multiqc_screen, f"{rp}/MULTIQC", partition)


def row_percentages(row):
    """Compute percentaligned, percentcomplexity, percentrip from row counts."""
    aligned = float(row.get("alignedreads") or 0)
    unaligned = float(row.get("unalignedreads") or 0)
    total = aligned + unaligned
    if total == 0 or aligned == 0:
        return 0.0, 0.0, 0.0
    pct_aligned = aligned * 100 / total
    unique = float(row.get("uniquealignedreads") or 0)
    pct_complexity = (unique * 100 / aligned) if aligned else 0
    rip = float(row.get("readsinpeaks") or 0)
    pct_rip = (rip * 100 / aligned) if aligned else 0
    return (
        round(pct_aligned, 3),
        round(pct_complexity, 3),
        round(pct_rip, 3),
    )


def format_pdf(value):
    """Return value if it looks like a PDF path, else 'NONE'."""
    if value and ".pdf" in str(value):
        return value
    return "NONE"


def choose_base_path(labname, labtype):
    """Return external or internal base path for the lab."""
    external = Path(f"/lab/htdata/Archived_Data/{labname}")
    internal = Path(f"/lab/solexa_public/{labname}")
    if external.is_dir():
        return external
    if internal.is_dir():
        return internal
    if labtype and "External" in str(labtype):
        return external
    return internal


def run(runfolder, htdatafolder, labid, config_path=None, partition=DEFAULT_PARTITION):
    """Main logic: DB query, create dirs, annotation files, and copyset jobs."""
    conn = get_connection(config_path)
    cursor = conn.cursor()

    runindex = get_run_index(cursor, runfolder)
    if runindex is None:
        print("Run folder not found in database. Exiting.")
        conn.close()
        sys.exit(0)

    print(f"Run folder found in database (RUNINDEX={runindex}).")
    rows = fetch_export_runinfo(cursor, runindex, labid)
    conn.close()

    if labid != "all" and len(rows) == 0:
        print(f"Lab ID '{labid}' not found in this run. Exiting.")
        return

    lab_paths = {}       # labname -> Path (runfolder for that lab)
    file_handles = {}    # labname -> open file
    lanes_done_unknown = set()  # LANE values for which we already ran copyset("unknown", ...)

    for row in rows:
        aligned = float(row.get("alignedreads") or 0)
        unaligned = float(row.get("unalignedreads") or 0)
        pct_aligned, pct_complexity, pct_rip = row_percentages(row)
        fapdf = format_pdf(row.get("fapdf"))
        bioapdf = format_pdf(row.get("bioapdf"))

        labname = row.get("labname")
        if labname not in lab_paths:
            rundate = runfolder.split("_")[0]
            laneannotationfilename = f"{rundate}_{labname}_laneannotation.xls"
            base = choose_base_path(labname, row.get("labtype"))
            ensure_delivery_dirs(base, runfolder)
            runfolder_path = base / runfolder
            lab_paths[labname] = runfolder_path

            annotation_path = runfolder_path / laneannotationfilename
            print(f"Creating {annotation_path}")
            fh = open(annotation_path, "w")
            fh.write(LANE_ANNOTATION_HEADER)
            file_handles[labname] = fh

        lane = row.get("LANE")
        lane = int(lane) if lane is not None else lane  # avoid float 1.0 in paths/set
        runfolder_path = lab_paths[labname]

        if lane not in lanes_done_unknown:
            lanes_done_unknown.add(lane)
            copyset("unknown", lane, htdatafolder, fapdf, bioapdf, runfolder_path, partition)

        barcode = (row.get("gtcid") or "").upper()
        copyset(barcode, lane, htdatafolder, fapdf, bioapdf, runfolder_path, partition)

        def get(key, default=""):
            v = row.get(key)
            return v if v is not None else default

        line = (
            f"{get('LANE')}\t{get('sampletype')}\t{get('organism')}\t\t{get('samplename')}\t"
            f"{get('barcode')}\t{get('insertrange')}\t{get('insertsize')}\t"
            f"{get('gtcid')}\t{get('lastname')}\t{get('labname')}\t"
            f"{get('adaptors')}\t{get('seqprimer')}\t{get('CYCLES')}\t{get('refgenome')}\t"
            f"{get('a260conc')}\t{get('qpcrconc')}\t{get('bioaconc')}\t{get('finallibraryqbitconc')}\t"
            f"{get('CONCUSED')}\t{get('nanobaseddf')}\t{get('dlf')}\t{get('ulinden')}\t"
            f"{get('ULLOADED')}\t{get('PMLOADED')}\t{get('equimolar')}\t"
            f"{get('FCID')}\t{get('SEQUENCER')}\t{get('QCRESULT')}\t"
            f"{get('totalreads')}\t{get('Q30')}\t{get('PF')}\t{get('alladapter')}\t"
            f"{pct_aligned}\t{pct_complexity}\t{get('numbofpeaks')}\t{pct_rip}\t"
            f"{get('INPUTSPECCONC')}\t{get('INPUTQBITCONC')}\t{get('LPCONCUSED')}\t"
            f"{get('INPUTAMOUNTUSED')}\t{get('LPMETHOD')}\t{get('AOINPUT')}\t"
            f"{get('PCRCYCLES')}\t{get('LIBRARYPREPQC')}\n"
        )
        file_handles[labname].write(line)

    for fh in file_handles.values():
        fh.close()


def main():
    argv = sys.argv[1:]
    partition = DEFAULT_PARTITION
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

    if len(argv) < 2:
        print("Usage: Make_Delivery_Package.py [--partition PARTITION] <htdatafolder> <labid> [runfolder]")
        print("  --partition: SLURM partition (default: solexa)")
        print("  htdatafolder = path to demux output (FASTQ, FASTQC, etc.); must be a directory")
        print("  labid        = lab id, 'all', or '1' (run once per distinct labid for this run)")
        print("  runfolder    = optional; RUNFOLDER for RUNINFO. If omitted, derived from htdatafolder (same rules as getQCinfo_by_runfolder.py)")
        sys.exit(1)

    htdatafolder = os.path.abspath(argv[0])
    if not os.path.isdir(htdatafolder):
        print(f"Error: htdatafolder is not a directory: {htdatafolder}", file=sys.stderr)
        sys.exit(1)

    labid = argv[1]
    runfolder_arg = argv[2] if len(argv) > 2 else None
    runfolder = resolve_runfolder(htdatafolder, runfolder_arg)
    print(f"Using runfolder: {runfolder}")

    if labid == "1":
        # Run for each distinct labid associated with this run
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                runindex = get_run_index(cursor, runfolder)
                if runindex is None:
                    print("Run folder not found in database. Exiting.")
                    sys.exit(0)
                labids = fetch_distinct_labids(cursor, runindex)
        finally:
            conn.close()
        if not labids:
            print("No lab IDs found for this run. Exiting.")
            sys.exit(0)
        for lid in labids:
            print(f"Running for labid: {lid}")
            run(runfolder, htdatafolder, lid, partition=partition)
    else:
        run(runfolder, htdatafolder, labid, partition=partition)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Update RUNINFO consumable fields (FCID, SEQKITLOT20, SEQKITLOT4, CLUSTERKITLOT, RUNFOLDER)
from RunParameters.xml (NovaSeq/MiSeq) or RunParameters.json (AVITI).
RUNFOLDER is set to YYMMDD_sequencer_flowcellid (e.g. 260122_WIGTC-NOVASEQ1A_AHF2Y3DSXF).

Finds runindex from localdir (same runfolder resolution as getQCinfo_by_runfolder).
Only updates if SEQDATE for that run is within the last 3 weeks; otherwise skips.

Usage:
  update_runinfo_consumables.py
      With no arguments: scan /lab/htdata/ (subfolders with A01100 or SH01116) and
      /lab/htdata/AV240904/ (subfolders with AV240904); update each if runfolder
      exists in DB and SEQDATE within 3 weeks. Report "run folder not found" and
      continue when a runfolder is missing.
  update_runinfo_consumables.py <localdir> [runfolder]
      Single run: update one localdir (optional runfolder).
"""
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

from db_config import get_connection
from runfolder_resolve import (
    RUN_PARAMETERS_JSON,
    RUN_PARAMETERS_XML,
    _get_json_value,
    _sequencer_type,
    get_flowcell_side,
    resolve_runfolder,
)

HTDATA_ROOT = "/lab/htdata"
AV240904_DIR = "/lab/htdata/AV240904"
NOVASEQ_SUBSTRING = "A01100"
MISEQ_SUBSTRING = "SH01116"
AVITI_SUBSTRING = "AV240904"


def get_runindex_and_seqdate(cursor, runfolder):
    """Return (runindex, seqdate) for runfolder from RUNINFO, or (None, None)."""
    cursor.execute(
        "SELECT RUNINDEX, SEQDATE FROM RUNINFO WHERE RUNFOLDER = %s",
        (runfolder,),
    )
    row = cursor.fetchone()
    if not row:
        return None, None
    return row["RUNINDEX"], row.get("SEQDATE")


def seqdate_within_weeks(seqdate, weeks=3):
    """Return True if seqdate is within the last `weeks` weeks (or today)."""
    if seqdate is None:
        return False
    if isinstance(seqdate, datetime):
        d = seqdate.date()
    elif hasattr(seqdate, "date"):
        d = seqdate.date()
    else:
        try:
            d = seqdate if hasattr(seqdate, "year") else datetime.strptime(str(seqdate)[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return False
    cutoff = datetime.now().date() - timedelta(weeks=weeks)
    return d >= cutoff


def _collect_batch_localdirs():
    """Return list of (localdir_path) to process when run with no arguments."""
    localdirs = []
    if os.path.isdir(HTDATA_ROOT):
        for name in os.listdir(HTDATA_ROOT):
            if NOVASEQ_SUBSTRING not in name and MISEQ_SUBSTRING not in name:
                continue
            path = os.path.join(HTDATA_ROOT, name)
            if os.path.isdir(path):
                localdirs.append(path)
    if os.path.isdir(AV240904_DIR):
        for name in os.listdir(AV240904_DIR):
            if AVITI_SUBSTRING not in name:
                continue
            path = os.path.join(AV240904_DIR, name)
            if os.path.isdir(path):
                localdirs.append(path)
    return localdirs


def read_aviti_consumables(localdir, on_error_exit=True):
    """
    Read RunParameters.json; return dict with FCID, SEQKITLOT20, SEQKITLOT4.
    FCID = FlowcellID; SEQKITLOT20 = Consumables.SequencingCartridge.LotNumber;
    SEQKITLOT4 = Consumables.Buffer.LotNumber.
    Returns None if file missing and on_error_exit is False.
    """
    path = Path(localdir) / RUN_PARAMETERS_JSON
    if not path.is_file():
        if on_error_exit:
            print(f"Error: {RUN_PARAMETERS_JSON} not found in {localdir}", file=sys.stderr)
            sys.exit(1)
        return None
    with open(path) as f:
        data = json.load(f)
    fcid = _get_json_value(data, "FlowcellID", "FlowcellId")
    if not fcid:
        # Fallback: Consumables.Flowcell.SerialNumber
        consumables = data.get("Consumables") or {}
        flowcell = consumables.get("Flowcell") or consumables.get("FlowCell") or {}
        fcid = flowcell.get("SerialNumber") or flowcell.get("SerialNumber")
    if not fcid:
        if on_error_exit:
            print("Error: FlowcellID (or Consumables.Flowcell.SerialNumber) not found in RunParameters.json", file=sys.stderr)
            sys.exit(1)
        return None
    consumables = data.get("Consumables") or {}
    seq_cart = consumables.get("SequencingCartridge") or {}
    buffer = consumables.get("Buffer") or {}
    seqkit20 = seq_cart.get("LotNumber") or ""
    seqkit4 = buffer.get("LotNumber") or ""
    return {"FCID": str(fcid).strip(), "SEQKITLOT20": str(seqkit20).strip(), "SEQKITLOT4": str(seqkit4).strip()}


def _find_text(root, tag):
    """First element with tag (any nesting); return text or None."""
    elem = root.find(f".//{tag}")
    return elem.text.strip() if elem is not None and elem.text else None


def read_novaseq_consumables(localdir, on_error_exit=True):
    """
    Read RunParameters.xml; return dict with FCID, SEQKITLOT20, SEQKITLOT4, CLUSTERKITLOT.
    FCID = side (A/B) + FlowCellSerialBarcode; SEQKITLOT20 = SbsLotNumber;
    SEQKITLOT4 = BufferLotNumber; CLUSTERKITLOT = ClusterLotNumber.
    Returns None if file missing or required fields missing and on_error_exit is False.
    """
    path = Path(localdir) / RUN_PARAMETERS_XML
    if not path.is_file():
        if on_error_exit:
            print(f"Error: {RUN_PARAMETERS_XML} not found in {localdir}", file=sys.stderr)
            sys.exit(1)
        return None
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError:
        if on_error_exit:
            raise
        return None
    try:
        side = get_flowcell_side(localdir)
    except SystemExit:
        if on_error_exit:
            raise
        return None
    barcode = _find_text(root, "FlowCellSerialBarcode")
    if not barcode:
        if on_error_exit:
            print("Error: FlowCellSerialBarcode not found in RunParameters.xml", file=sys.stderr)
            sys.exit(1)
        return None
    fcid = f"{side}{barcode}"
    seqkit20 = _find_text(root, "SbsLotNumber") or ""
    seqkit4 = _find_text(root, "BufferLotNumber") or ""
    clusterlot = _find_text(root, "ClusterLotNumber") or ""
    return {
        "FCID": fcid,
        "SEQKITLOT20": seqkit20,
        "SEQKITLOT4": seqkit4,
        "CLUSTERKITLOT": clusterlot,
    }


def process_one(localdir, runfolder_arg, cursor, batch=False):
    """
    Process one localdir: resolve runfolder, check runindex/SEQDATE, update if applicable.
    Returns: "updated", "not_found", "skipped_old", or "skip" (missing RunParameters in batch).
    When batch is True and runfolder not in DB, prints message and returns "not_found".
    """
    on_error_exit = not batch
    runfolder = resolve_runfolder(localdir, runfolder_arg)
    if not batch:
        print(f"Using runfolder: {runfolder}")

    seq_type = _sequencer_type(localdir)
    if seq_type is None:
        if on_error_exit:
            print("Error: Sequencer not supported.", file=sys.stderr)
            sys.exit(1)
        return "skip"

    runindex, seqdate = get_runindex_and_seqdate(cursor, runfolder)
    if runindex is None:
        print(f"Run folder not found: {runfolder}")
        return "not_found"
    if not seqdate_within_weeks(seqdate, weeks=3):
        if not batch:
            print(f"SEQDATE {seqdate} is not within the last 3 weeks. Exiting without update.")
        return "skipped_old"

    if seq_type == "aviti":
        vals = read_aviti_consumables(localdir, on_error_exit=on_error_exit)
    else:
        vals = read_novaseq_consumables(localdir, on_error_exit=on_error_exit)
    if vals is None:
        return "skip"

    # RUNFOLDER = YYMMDD_sequencer_flowcellid (runfolder from resolve_runfolder is already in this form)
    if seq_type == "aviti":
        sql = (
            "UPDATE RUNINFO SET FCID = %s, SEQKITLOT20 = %s, SEQKITLOT4 = %s, RUNFOLDER = %s "
            "WHERE RUNINDEX = %s"
        )
        params = (vals["FCID"], vals["SEQKITLOT20"], vals["SEQKITLOT4"], runfolder, runindex)
    else:
        sql = (
            "UPDATE RUNINFO SET FCID = %s, SEQKITLOT20 = %s, SEQKITLOT4 = %s, CLUSTERKITLOT = %s, RUNFOLDER = %s "
            "WHERE RUNINDEX = %s"
        )
        params = (vals["FCID"], vals["SEQKITLOT20"], vals["SEQKITLOT4"], vals["CLUSTERKITLOT"], runfolder, runindex)

    cursor.execute(sql, params)
    if not batch:
        print(f"Run found (RUNINDEX={runindex}, SEQDATE={seqdate}). Within 3 weeks; proceeding.")
        print(f"Updated RUNINFO for RUNINDEX={runindex}: {list(vals.keys())}")
    return "updated"


def main():
    batch_mode = len(sys.argv) < 2

    if batch_mode:
        localdirs = _collect_batch_localdirs()
        if not localdirs:
            print("No matching subfolders found under /lab/htdata/ or /lab/htdata/AV240904/.")
            return
        print(f"Batch mode: processing {len(localdirs)} folder(s).")
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                for localdir in localdirs:
                    print(f"--- {localdir} ---")
                    try:
                        result = process_one(localdir, None, cursor, batch=True)
                        if result == "updated":
                            conn.commit()
                            print(f"Updated: {localdir}")
                        elif result == "not_found":
                            pass  # already printed in process_one
                        elif result == "skipped_old":
                            print("Skipped (SEQDATE not within 3 weeks).")
                        elif result == "skip":
                            print("Skipped (missing or invalid RunParameters).")
                    except SystemExit as e:
                        if e.code and e.code != 0:
                            print("Skipped (error resolving runfolder or reading parameters).")
                        else:
                            raise
                    except Exception as e:
                        print(f"Error: {e}")
        finally:
            conn.close()
        return

    # Single-run mode
    localdir = os.path.abspath(sys.argv[1])
    if not os.path.isdir(localdir):
        print(f"Error: localdir is not a directory: {localdir}", file=sys.stderr)
        sys.exit(1)

    runfolder_arg = sys.argv[2] if len(sys.argv) > 2 else None
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            result = process_one(localdir, runfolder_arg, cursor, batch=False)
            if result == "not_found":
                print("Run folder not found in database. Exiting without update.")
                sys.exit(0)
            if result == "skipped_old":
                sys.exit(0)
            if result == "skip":
                sys.exit(1)
            conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()

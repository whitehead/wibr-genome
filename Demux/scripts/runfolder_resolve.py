"""
Shared runfolder resolution for demux scripts.
Derives RUNFOLDER for DB lookup from a data directory (localdir / htdatafolder).

Supported sequencers (directory name must contain one):
  - _A01100_  : NovaSeq; RunParameters.xml <side>; runfolder date_WIGTC-NOVASEQ1A/B_flowcellid
  - _AV240904_: AVITI; RunParameters.json (FlowcellID, side sideA/sideB, Date); runfolder YYMMDD_WIGTC-AVITI1A/B_flowcellid
Otherwise exits with "sequencer not compatible".
"""
import os
import sys
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

RUN_PARAMETERS_XML = "RunParameters.xml"
RUN_PARAMETERS_JSON = "RunParameters.json"

NOVASEQ_MARKER = "_A01100_"
AVITI_MARKER = "_AV240904_"


def _sequencer_type(localdir):
    """Return 'novaseq', 'aviti', or None if localdir basename is not compatible."""
    basename = os.path.basename(os.path.abspath(localdir.rstrip(os.sep)))
    if NOVASEQ_MARKER in basename:
        return "novaseq"
    if AVITI_MARKER in basename:
        return "aviti"
    return None


def get_flowcell_side(localdir):
    """
    Read RunParameters.xml in localdir and return flowcell side 'A' or 'B'.
    Exits with error if file is missing or <side> not found.
    """
    path = Path(localdir) / RUN_PARAMETERS_XML
    if not path.is_file():
        print(f"Error: {RUN_PARAMETERS_XML} not found in {localdir}", file=sys.stderr)
        sys.exit(1)
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"Error: Failed to parse {path}: {e}", file=sys.stderr)
        sys.exit(1)
    for tag in ("side", "Side"):
        elem = root.find(f".//{tag}")
        if elem is not None and elem.text:
            side = elem.text.strip().upper()
            if side in ("A", "B"):
                return side
    print(f"Error: Could not find <side>A</side> or <side>B</side> in {path}", file=sys.stderr)
    sys.exit(1)


def _date_to_yymmdd(date_str):
    """Convert Date string like '2026-01-07T12:50:30.785605991Z' to YYMMDD e.g. 260107."""
    if not date_str or not isinstance(date_str, str):
        return None
    s = date_str.strip()
    if not s:
        return None
    try:
        if "T" in s:
            s = s.split("T")[0]
        dt = datetime.strptime(s[:10], "%Y-%m-%d")
        return dt.strftime("%y%m%d")
    except (ValueError, IndexError):
        return None


def _get_json_value(obj, *keys):
    """Get value from nested dict by trying each key at top level, then in common nested keys."""
    if isinstance(obj, dict):
        for k in keys:
            if k in obj:
                return obj[k]
        for v in obj.values():
            if isinstance(v, dict):
                found = _get_json_value(v, *keys)
                if found is not None:
                    return found
    return None


def get_aviti_runfolder(localdir):
    """
    Read RunParameters.json in localdir; return runfolder = YYMMDD_WIGTC-AVITI1A/B_FlowcellID.
    Exits with error if file missing or required parameters (FlowcellID, side, Date) not found.
    """
    path = Path(localdir) / RUN_PARAMETERS_JSON
    if not path.is_file():
        print(f"Error: {RUN_PARAMETERS_JSON} not found in {localdir}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: Failed to read {path}: {e}", file=sys.stderr)
        sys.exit(1)
    flowcell_id = _get_json_value(data, "FlowcellID", "FlowcellId")
    side_val = _get_json_value(data, "side", "Side")
    date_val = _get_json_value(data, "Date", "date")
    if not flowcell_id:
        print(f"Error: FlowcellID not found in {path}", file=sys.stderr)
        sys.exit(1)
    if not side_val:
        print(f"Error: side not found in {path}", file=sys.stderr)
        sys.exit(1)
    side_str = str(side_val).strip().lower()
    if side_str == "sidea":
        suffix = "A"
    elif side_str == "sideb":
        suffix = "B"
    else:
        print(f"Error: side must be sideA or sideB in {path}, got {side_val!r}", file=sys.stderr)
        sys.exit(1)
    yymmdd = _date_to_yymmdd(date_val) if date_val else None
    if not yymmdd:
        print(f"Error: Date not found or not parseable in {path}", file=sys.stderr)
        sys.exit(1)
    sequencer = f"WIGTC-AVITI1{suffix}"
    return f"{yymmdd}_{sequencer}_{flowcell_id}"


def resolve_runfolder(localdir, runfolder_arg=None):
    """
    Return runfolder for DB lookup. If runfolder_arg is given, use it.
    Otherwise derive from localdir:
    - localdir name must contain _A01100_ (NovaSeq) or _AV240904_ (AVITI); else exit "sequencer not compatible".
    - NovaSeq: RunParameters.xml <side>; format date_WIGTC-NOVASEQ1A/B_flowcellid.
    - AVITI: RunParameters.json (FlowcellID, side, Date); format YYMMDD_WIGTC-AVITI1A/B_flowcellid.
    """
    if runfolder_arg is not None and runfolder_arg != "":
        return runfolder_arg
    seq_type = _sequencer_type(localdir)
    if seq_type is None:
        print(
            "Error: Sequencer not compatible. localdir name must contain _A01100_ (NovaSeq) or _AV240904_ (AVITI).",
            file=sys.stderr,
        )
        sys.exit(1)
    if seq_type == "aviti":
        return get_aviti_runfolder(localdir)
    # NovaSeq
    side = get_flowcell_side(localdir)
    basename = os.path.basename(os.path.abspath(localdir.rstrip(os.sep)))
    parts = basename.split("_")
    if len(parts) >= 4:
        sequencer = "WIGTC-NOVASEQ1A" if side == "A" else "WIGTC-NOVASEQ1B"
        return f"{parts[0]}_{sequencer}_{'_'.join(parts[3:])}"
    return basename

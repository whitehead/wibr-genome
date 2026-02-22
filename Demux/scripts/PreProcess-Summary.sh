#!/bin/bash
# Script to generate fastq and fastqscreen summary files using MULTIQC


set -e
set -u
set -o pipefail

##check arguments
if [ "$#" -ne 2 ]; then
    printf "Usage: $(basename $0) [-r runfolder]\n";
    exit
fi

while getopts ":r:" OPTION; do
    case $OPTION in
        r)
            runfolder=$OPTARG
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
	    echo "script usage: $(basename $0) [-r read1fastq (gz file only)]" >&2
            exit 1
            ;;
        :)
            echo "Option -$OPTARG missing" >&2
	    echo "script usage: $(basename $0) [-r read1fastq (gz file only)]" >&2
            exit 1
            ;;
        h)
            echo -e "-h print this screen and exit"
            exit $E_OPTERROR
            ;;
    esac
done
shift $((OPTIND -1))

outdir="${runfolder}/FASTQ/"
FASTQCdir="${runfolder}/FASTQC/"
FASTQSCREENdir="${runfolder}/FASTQSCREEN"

#create output director if does not exit
if [ ! -d "$outdir" ]; then
  mkdir $outdir
else
  echo "Output Directory Already Exists"
fi

#create fastqc director if does not exit
if [ ! -d "$FASTQCdir" ]; then
  mkdir $FASTQCdir
else
  echo "fastqc Directory Already Exists"
  #rm -rf $FASTQCdir
  #mkdir $FASTQCdir
fi

#create fastqc director if does not exit
if [ ! -d "$FASTQSCREENdir" ]; then
  mkdir $FASTQSCREENdir
else
  echo "fastqc Directory Already Exists"
  #rm -rf $FASTQSCREENdir
  #mkdir $FASTQSCREENdir
fi

#random number generator
RANDOM=$$
jobid=$RANDOM

cd $runfolder

##creates log file with input commands
#echo "Log file $(date +%y_%m_%d)" > $runfolder/log_file.txt;
#echo "Command line input: "$0" "$@>>$runfolder/log_file.txt;
#echo "RUN Folder file: $runfolder" >>$runfolder/log_file.txt;

cd $outdir

multiqc --force --cl-config '{max_table_rows: 20000}' ../FASTQC/ --outdir ../FASTQC/

declare -a lanes=(1 2 3 4 5 6 7 8)

for i in "${!lanes[@]}"
do
    if compgen -G "${FASTQCdir}/*_L00${lanes[$i]}*" > /dev/null; then
        multiqc --force --cl-config '{max_table_rows: 20000}' --outdir ../MULTIQC/ --filename FASTQC_MULTIQC_L${lanes[$i]}_Interactive ../FASTQC/*_L00${lanes[$i]}*
    fi

    if compgen -G "${FASTQSCREENdir}/*_L00${lanes[$i]}*" > /dev/null; then
        multiqc --force --cl-config '{max_table_rows: 20000}' --outdir ../MULTIQC/ --filename FASTQSCREEN_MULTIQC_L${lanes[$i]}_Interactive ../FASTQSCREEN/*_L00${lanes[$i]}*
    fi
done

for i in "${!lanes[@]}"
do
    if compgen -G "${FASTQCdir}/*_L${lanes[$i]}*" > /dev/null; then
        multiqc --force --cl-config '{max_table_rows: 20000}' --outdir ../MULTIQC/ --filename FASTQC_MULTIQC_L${lanes[$i]}_Interactive ../FASTQC/*_L${lanes[$i]}*
    fi

    if compgen -G "${FASTQSCREENdir}/*_L${lanes[$i]}*" > /dev/null; then
        multiqc --force --cl-config '{max_table_rows: 20000}' --outdir ../MULTIQC/ --filename FASTQSCREEN_MULTIQC_L${lanes[$i]}_Interactive ../FASTQSCREEN/*_L${lanes[$i]}*
    fi
done

#!/bin/bash


set -e
set -u
set -o pipefail

PARTITION="solexa"

##check arguments
if [ "$#" -lt 2 ]; then
    printf "Usage: $(basename $0) -r runfolder [-p partition]\n";
    printf "  -r runfolder  (required)\n";
    printf "  -p partition  SLURM partition (default: solexa)\n";
    exit 1
fi

while getopts ":r:p:" OPTION; do
    case $OPTION in
        r)
            runfolder=$OPTARG
            ;;
        p)
            PARTITION=$OPTARG
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            echo "Usage: $(basename $0) -r runfolder [-p partition]" >&2
            exit 1
            ;;
        :)
            echo "Option -$OPTARG missing" >&2
            echo "Usage: $(basename $0) -r runfolder [-p partition]" >&2
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

SLURM_OUTDIR="/lab/htdata/SLURM"
for i in *gz; do sbatch --mem=4gb --cpus-per-task=2 --partition="${PARTITION}" --output "${SLURM_OUTDIR}/%j.out" --error "${SLURM_OUTDIR}/%j.err" --wrap "fastqc --noextract --format fastq --threads 4 -o ${FASTQCdir} $i"; done

for i in *gz; do sbatch --mem=4gb --cpus-per-task=2 --partition="${PARTITION}" --output "${SLURM_OUTDIR}/%j.out" --error "${SLURM_OUTDIR}/%j.err" --wrap "fastq_screen --conf /lab/htdata/fastq_screen.conf --outdir ${FASTQSCREENdir} --aligner bowtie2 --force --subset 1000000 $i"; done





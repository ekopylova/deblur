#!/usr/bin/env python

# ----------------------------------------------------------------------------
# Copyright (c) 2015, The Deblur Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

import click
from os import listdir
from os.path import dirname, join, isfile, exists
from glob import glob

from skbio.parse.sequences import parse_fasta
from biom.util import biom_open, HAVE_H5PY
from qiime.util import split_sequence_file_on_sample_ids_to_files

from deblur.deblurring import deblur
from deblur.workflow import (launch_workflow, trim_seqs, dereplicate_seqs,
                             remove_artifacts_seqs,
                             multiple_sequence_alignment,
                             remove_chimeras_denovo_from_seqs,
                             generate_biom_table)
from deblur.parallel_deblur import ParallelDeblur

@click.group()
def deblur_cmds():
    pass


# LAUNCH FULL DEBLUR PIPELINE COMMAND
@deblur_cmds.command()
@click.option('--seqs-fp', required=True,
                type=click.Path(resolve_path=True, readable=True, exists=True,
                                file_okay=True),
              help="Demultiplexed FASTA/Q file including all samples")
@click.option('--output-fp', required=True,
                type=click.Path(resolve_path=True, readable=True, exists=False,
                                file_okay=True),
              help="Filepath to output BIOM table")
@click.option('--ref-fp', required=True, multiple=True,
              type=click.Path(resolve_path=True, readable=True, exists=True,
                              file_okay=True),
              help="Keep all sequences aligning to this FASTA database "
                   "(for multiple databases, use "
                   "--ref-fp db1.fa --ref-fp db2.fa ..)")
@click.option('--ref-db-fp', required=False, multiple=True,
              type=click.Path(resolve_path=True, readable=True, exists=False,
                              file_okay=True),
              help="Keep all sequences aligning to this indexed "
                   "database. For multiple databases, the order "
                   "must follow that of --ref-fp, for example, "
                   "--ref-db-fp db1.idx --ref-db-fp db2.idx ..")
@click.option('--file-type', required=False,
              type=click.Choice(['fasta', 'fastq']), default=['fasta'],
              show_default=True, help="Type of file")
@click.option('--read-error', '-e', required=False, type=float, default=0.05,
              show_default=True, help="Read error rate")
@click.option('--mean-error', '-m', required=False, type=float, default=None,
              show_default=True,
              help="The mean error, used for original sequence estimate. If "
                   "not passed the same value as --read-error will be used")
@click.option('--error-dist', '-d', required=False, type=str, default=None,
              show_default=True,
              help="A comma separated list of error probabilities for each "
                   "hamming distance. The length of the list determines the "
                   "number of hamming distances taken into account.")
@click.option('--indel-prob', '-i', required=False, type=float, default=0.01,
              show_default=True,
              help='Insertion/deletion (indel) probability '
                   '(same for N indels)')
@click.option('--indel-max', required=False, type=int, default=3,
              show_default=True,
              help="Maximal indel number")
@click.option('--trim-length', '-t', required=False, type=int, default=100,
              show_default=True, help="Sequence trim length")
@click.option('--min-size', required=False, type=int, default=2,
              show_default=True, help="Discard sequences with an abundance "
              "value smaller than min-size")
@click.option('--negate', '-n', required=False, default=False,
              show_default=True, type=bool,
              help="Discard all sequences aligning to the database "
                   "passed via --ref-fp option")
@click.option('--threads', '-a', required=False, type=int,
              default=1, show_default=True,
              help="Number of threads to use for SortMeRNA")
@click.option('--delim', required=False, type=str, default='_',
              show_default=True, help="Delimiter in FASTA labels to separate "
                                      "sample ID from sequence ID")
@click.option('--buffer-size', required=False, type=int, default=500,
              show_default=True, help="The number of sequences to read into "
              "memory before writing to file (for splitting input file by "
              "sample)")
@click.option('--jobs-to-start', '-O', required=False, type=int, default=1,
              show_default=True,
              help="Number of jobs to start (if to run in parallel)")
@click.option('--retain-temp-files', required=False, type=bool, default=False,
              show_default=True,
              help="Retain temporary files after parallel runs complete "
                   "(useful for debugging)")
@click.option('--suppress-polling', required=False, type=bool, default=False,
              show_default=True,
              help="Suppress polling of jobs and merging of results upon "
                   "completion")
def workflow(seqs_fp, output_fp, file_type, read_error, mean_error,
             error_dist, indel_prob, indel_max, trim_length, min_size,
             ref_fp, ref_db_fp, negate, threads, delim, buffer_size,
             jobs_to_start, retain_temp_files, suppress_polling):
    """Launch deblur workflow in parallel"""
    # If the user provided an error_dist value, we map it to a list of floats
    if error_dist:
        error_dist = list(map(float, error_dist.split(',')))
    out_dir = dirname(output_fp)
    # Split demultiplexed FASTA on sample IDs
    out_dir_split = join(out_dir, "split")
    if not exists(out_dir_split):
        with open(seqs_fp, 'U') as seqs_f:
            split_sequence_file_on_sample_ids_to_files(
                seqs_f,
                file_type,
                out_dir_split,
                buffer_size)
    # Run deblur in parallel
    params = {}
    input_fps = glob('%s/*' % out_dir_split)
    params['ref_db_fp'] = ref_db_fp
    params['ref_fp'] = ref_fp
    params['jobs_to_start'] = jobs_to_start
    # Number of samples written
    samples_fp = [f for f in listdir(out_dir_split) if isfile(f)]
    parallel_runner = ParallelDeblur(
        jobs_to_start=jobs_to_start,
        retain_temp_files=retain_temp_files,
        suppress_polling=suppress_polling)
    parallel_runner(
        input_fp=input_fps,
        output_dir=out_dir,
        params=params)
    # Merge OTU tables
    all_bioms = glob('%s/*.biom' % out_dir)
    merge_otu_tables(output_fp, all_bioms)


if __name__ == '__main__':
    deblur_cmds()
"""
Task: Count number of rows for each school in the csv file

Setup instructions: https://cloud.google.com/dataflow/docs/quickstarts/quickstart-python

Source modified from https://github.com/apache/beam/blob/master/sdks/python/apache_beam/examples/wordcount_minimal.py
Followed tutorial at https://beam.apache.org/get-started/wordcount-example/

set GOOGLE_APPLICATION_CREDENTIALS to a service account with BigQuery Data Editor, Dataflow Admin roles to execute on Google Cloud Dataflow without 403

The following is the command to run on Google Cloud Dataflow:
    export DATAINDEX=0
    bin/python -m school_aggregator --input gs://pankaj-dataflow-jobs/MERGED2014_15_PP.csv \
                                             --output gs://pankaj-dataflow-jobs/counts_$DATAINDEX \
                                             --table pankaj.70MB_schools_$DATAINDEX \
                                             --runner DataflowRunner \
                                             --project hilliao-on-justinburke \
                                             --temp_location gs://pankaj-dataflow-jobs/tmp/ \
                                             --stage_location gs://pankaj-dataflow-jobs/stage/ \
                                             --job_name pankaj-school-work-$DATAINDEX \

Run locally without writing to BigQuery:
    bin/python -m school_aggregator --output out --input input.csv --runner DirectRunner
"""

from __future__ import absolute_import

import argparse
import logging

import apache_beam as beam
from apache_beam.io import WriteToText
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.options.pipeline_options import SetupOptions


def run(argv=None):
    """Main entry point; defines and runs the pipeline."""

    parser = argparse.ArgumentParser()
    parser.add_argument('--input',
                        dest='input',
                        default='gs://pankaj-dataflow-jobs/MERGED2014_15_PP.csv',
                        help='Input file to process.')
    parser.add_argument('--table',
                        dest='table',
                        default=None,
                        help='Cloud BigQuery dataset.table name.')
    parser.add_argument('--output',
                        dest='output',
                        # CHANGE 1/5: The Google Cloud Storage path is required
                        # for outputting the results.
                        default='gs://pankaj-dataflow-jobs/sample-out',
                        help='Output file to write results to.')
    parser.add_argument('--runner',
                        dest='runner',
                        default='DataflowRunner',
                        help='DataflowRunner or DirectRunner')
    parser.add_argument('--project',
                        dest='project',
                        default='hilliao-on-justinburke',
                        help='Google Cloud Project ID')
    parser.add_argument('--stage_location',
                        dest='stage_location',
                        default='gs://pankaj-dataflow-jobs/stage/',
                        help='Google Cloud Storage path for staging Dataflow files')
    parser.add_argument('--temp_location',
                        dest='temp_location',
                        default='gs://pankaj-dataflow-jobs/stage/',
                        help='Google Cloud Storage path for staging Dataflow files')
    parser.add_argument('--job_name',
                        dest='job_name',
                        default='pankaj-school-work',
                        help='Google Cloud Storage path for staging Dataflow files')
    known_args, pipeline_args = parser.parse_known_args(argv)
    pipeline_args.extend([
        '--runner=%s' % known_args.runner,
        '--project=%s' % known_args.project,
        '--staging_location=%s' % known_args.stage_location,
        '--temp_location=%s' % known_args.temp_location,
        '--job_name=%s' % known_args.job_name,
    ])

    # We use the save_main_session option because one or more DoFn's in this
    # workflow rely on global context (e.g., a module imported at module level).
    pipeline_options = PipelineOptions(pipeline_args)
    pipeline_options.view_as(SetupOptions).save_main_session = True
    with beam.Pipeline(options=pipeline_options) as p:
        class Split(beam.DoFn):
            def process(self, element):
                row = element.split(",")
                if row[0].encode('utf8')[3:] != "UNITID":
                    byschool = row[3], row[0]
                    # needs to be an array to avoid ValueError: Number of components does not match number of coders. [while running 'ParDo(Split)']
                    return [byschool]

        # Read the text file into a PCollection of rows
        lines = p | beam.io.ReadFromText(known_args.input) | beam.ParDo(Split())

        # Count the occurrences of each school
        counts = lines | 'Group by school as key' >> beam.combiners.Count.PerKey()

        # Format the counts into a PCollection of school, count dictionary
        def format_result(school_count):
            # (word, count) = school_count
            return '{school: \'%s\', count: %s}' % (school_count['name'], school_count['count'])

        school_count = counts | 'name the key, value' >> beam.Map(lambda x: {'name': x[0], 'count': x[1]})
        text_output = school_count | 'Format each row' >> beam.Map(format_result)

        # Write to the specific output file locally or in Google Cloud Storage
        text_output | 'writing to the output text file' >> WriteToText(known_args.output)
        if known_args.table is not None:
            school_count | 'writing to Cloud BigQuery' >> beam.io.WriteToBigQuery(
                known_args.table,
                schema='name:STRING, count:INTEGER',
                create_disposition=beam.io.BigQueryDisposition.CREATE_IF_NEEDED,
                write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND)


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    run()

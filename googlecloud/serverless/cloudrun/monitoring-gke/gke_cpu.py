import datetime
import os
import sys
from concurrent import futures
from concurrent.futures.thread import ThreadPoolExecutor

import opencensus.trace.tracer
from flask import Flask
from gcloud import pubsub  # used to get current project ID
from google.cloud import error_reporting
from google.cloud import logging
from google.cloud import monitoring_v3
from google.cloud import resource_manager
from opencensus.ext.stackdriver import trace_exporter as stackdriver_exporter

#     DEFAULT = 0
#     DEBUG = 100
#     INFO = 200
#     NOTICE = 300
#     WARNING = 400
#     ERROR = 500
#     CRITICAL = 600
#     ALERT = 700
#     EMERGENCY = 800
LOG_SEVERITY_INFO = 'INFO'
LOG_SEVERITY_DEFAULT = 'DEFAULT'
LOG_SEVERITY_WARNING = 'WARNING'
LOG_SEVERITY_DEBUG = 'DEBUG'
LOG_SEVERITY_NOTICE = 'NOTICE'
MAX_WORKERS = os.getenv('MAX_THREADS', 20)

app_name = 'monitoring_gke_node_cpu'

try:
    import googleclouddebugger

    googleclouddebugger.enable()
except:
    for e in sys.exc_info():
        print(e)


def initialize_tracer(project_id):
    exporter = stackdriver_exporter.StackdriverExporter(
        project_id=project_id
    )
    tracer = opencensus.trace.tracer.Tracer(
        exporter=exporter,
        sampler=opencensus.trace.tracer.samplers.AlwaysOnSampler()
    )

    return tracer


pubsub_client = pubsub.Client()
gcp_log_trace_project_id = os.getenv('GCP_PROJECT', pubsub_client.project)
tracer = initialize_tracer(gcp_log_trace_project_id)
error_reporting_client = error_reporting.Client()
logging_client = logging.Client()
logger = logging_client.logger(app_name)

app = Flask(__name__)


@app.route('/health', methods=['GET'])
def health_check():
    import flask
    return 'Running Flask {0} on Python {1}!\n'.format(flask.__version__, sys.version)


def get_projects(id_filter):
    client = resource_manager.Client()
    id_filter = {'id': id_filter}
    projects = []
    for project in client.list_projects(id_filter):
        projects.append(project.project_id)

    return projects


# '2020-10-24_00:00:00', '2020-10-25_00:00:00', 3600)
def get_avg_cpu_cores(project_id, GKE_project_id, start_time, end_time, alignment_period_seconds):
    client = monitoring_v3.MetricServiceClient()
    project_name = f"projects/{project_id}"
    start = datetime.datetime.strptime(start_time, '%Y-%m-%d_%H:%M:%S')
    end = datetime.datetime.strptime(end_time, '%Y-%m-%d_%H:%M:%S')

    interval = monitoring_v3.TimeInterval(
        {
            "end_time": {"seconds": int(end.timestamp())},
            "start_time": {"seconds": int(start.timestamp())},
        }
    )

    aggregation = monitoring_v3.Aggregation(
        {
            "alignment_period": {"seconds": alignment_period_seconds},
            "per_series_aligner": monitoring_v3.Aggregation.Aligner.ALIGN_MEAN,
            "cross_series_reducer": monitoring_v3.Aggregation.Reducer.REDUCE_SUM,
        }
    )

    cpu_cores = 0
    with tracer.start_span(name=f"{app_name} get {GKE_project_id}'s metrics") as trace_span:
        results = client.list_time_series(
            request={
                "name": project_name,
                "filter": 'metric.type = "kubernetes.io/node/cpu/total_cores" AND resource.type="k8s_node" AND project= ' +
                          GKE_project_id,
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                "aggregation": aggregation,
            }
        )

        total = 0.0
        for result in results:
            logger.log_text(f"data points collected: {len(result.points)}", severity=LOG_SEVERITY_DEBUG)
            for point in result.points:
                total += point.value.double_value

            cpu_cores += total / len(result.points)

    return cpu_cores


@app.route('/projects/<project_id_glob>/start-datetime/<start>/end-datetime/<end>/alignment_period_seconds/<secs>',
           methods=['GET'])
def get_gke_cpu(project_id_glob, start, end, secs):
    total = 'total_cpu'

    with tracer.start_span(name=f"{app_name}:get_gke_cpu") as outer_trace_span:
        with outer_trace_span.span(name=f"get_projects({project_id_glob})") as get_proj_span:
            projects = get_projects(project_id_glob)

        resp = {total: 0}
        thread_results = {}

        with outer_trace_span.span(name=f"get_metrics()") as get_metrics_span:
            with ThreadPoolExecutor(max_workers=int(MAX_WORKERS)) as executor:
                for project_id in projects:
                    thread_results[project_id] = executor.submit(get_avg_cpu_cores, os.environ['MON_PROJECT_ID'],
                                                                 project_id, start, end, int(secs))
                futures.wait(thread_results.values(), return_when=futures.ALL_COMPLETED)

            for project_id in thread_results:
                # exception thrown from .result() method if any exception happened
                try:
                    thread_results[project_id] = thread_results[project_id].result()
                    if thread_results[project_id]:
                        resp[total] += thread_results[project_id]
                        resp[project_id] = thread_results[project_id]
                except Exception as ex:
                    error_reporting_client.report_exception()
                    thread_results[project_id] = ex
                    resp[project_id] = str(ex)

    return resp


if __name__ == "__main__":
    app.run(debug=True, threaded=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

import json


def log(text: str, severity: str):
    """
    Logs a message as structured JSON so Cloud Logging records the severity:
    https://cloud.google.com/run/docs/logging#using-json

    Args:
        text: The message to log.
        severity: The severity of the message (e.g., "ERROR", "WARNING").
    """
    print(json.dumps({'severity': severity, 'message': text}), flush=True)


LOG_SEVERITY_ERROR = "ERROR"
LOG_SEVERITY_WARNING = "WARNING"
LOG_SEVERITY_DEBUG = "DEBUG"

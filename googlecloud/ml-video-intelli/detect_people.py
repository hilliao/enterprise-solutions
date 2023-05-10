# https://cloud.google.com/video-intelligence/docs/people-detection
import os
from google.cloud import videointelligence_v1 as videointelligence
from google.cloud import logging
import argparse

LOG_SEVERITY_INFO = 'INFO'
LOG_SEVERITY_DEFAULT = 'DEFAULT'
LOG_SEVERITY_WARNING = 'WARNING'
LOG_SEVERITY_DEBUG = 'DEBUG'
LOG_SEVERITY_NOTICE = 'NOTICE'

client = logging.Client()
PROJECT_ID = os.environ["PROJECT_ID"]
logger = client.logger(name=PROJECT_ID)


def detect_people(gcs_uri: str = 'gs://bucket/video.mp4', timeout: int = 300):
    """Detects people in a video."""

    api_client = videointelligence.VideoIntelligenceServiceClient()

    # Configure the request
    config = videointelligence.types.PersonDetectionConfig(
        include_bounding_boxes=True,
        include_attributes=True,
        include_pose_landmarks=True,
    )
    context = videointelligence.types.VideoContext(person_detection_config=config)
    logger.log_text("Starting video intelligence API request...", severity=LOG_SEVERITY_DEBUG)

    # Start the asynchronous request
    operation = api_client.annotate_video(
        request={
            "features": [videointelligence.Feature.PERSON_DETECTION],
            "input_uri": gcs_uri,
            "video_context": context,
        }
    )

    print("\nProcessing video for person detection annotations at timeout {} on uri {}".format(timeout, gcs_uri))
    log_dict = {
        'message': "Processing video for person detection annotations",
        'file': gcs_uri,
        'timeout': timeout,
    }
    logger.log_struct(log_dict, severity=LOG_SEVERITY_DEBUG)
    result = operation.result(timeout=timeout)

    print("\nFinished processing.\n")

    # Retrieve the first result, because a single video was processed.
    annotation_result = result.annotation_results[0]

    detected_people = []

    for annotation in annotation_result.person_detection_annotations:
        print("Person detected:")
        for track in annotation.tracks:
            detected_track = {
                "start": track.segment.start_time_offset.seconds + track.segment.start_time_offset.microseconds / 1e6,
                "end": track.segment.end_time_offset.seconds + track.segment.end_time_offset.microseconds / 1e6,
            }
            print(
                "Segment: {}s to {}s".format(
                    detected_track["start"],
                    detected_track["end"],
                )
            )

            # Each segment includes timestamped objects that include
            # characteristics - -e.g.clothes, posture of the person detected.
            # Grab the first timestamped object
            timestamped_object = track.timestamped_objects[0]
            box = timestamped_object.normalized_bounding_box
            detected_track["left"] = box.left
            detected_track["top"] = box.top
            detected_track["right"] = box.right
            detected_track["bottom"] = box.bottom
            print("Bounding box:")
            print("\tleft  : {}".format(detected_track["left"]))
            print("\ttop   : {}".format(detected_track["top"]))
            print("\tright : {}".format(detected_track["right"]))
            print("\tbottom: {}".format(detected_track["bottom"]))

            # Attributes include unique pieces of clothing,
            # poses, or hair color.
            print("Attribute name, value at confidence:")
            detected_people_attributes = []
            for attribute in timestamped_object.attributes:
                detected_people_attributes.append(
                    {
                        "{}:{}".format(attribute.name, attribute.value): attribute.confidence
                    }
                )
                print(
                    "\t{}:{} at confidence {}".format(
                        attribute.name, attribute.value, attribute.confidence
                    )
                )
            detected_track["attributes"] = detected_people_attributes

            # Landmarks in person detection include body parts such as
            # left_shoulder, right_ear, and right_ankle
            print("Landmarks:")
            detected_people_landmarks = []
            for landmark in timestamped_object.landmarks:
                detected_people_landmarks.append(
                    {
                        landmark.name: {
                            "confidence": landmark.confidence,
                            "x": landmark.point.x,  # Normalized vertex
                            "y": landmark.point.y,  # Normalized vertex
                        }
                    }
                )
                print(
                    "\t{}: {} (x={}, y={})".format(
                        landmark.name,
                        landmark.confidence,
                        landmark.point.x,  # Normalized vertex
                        landmark.point.y,  # Normalized vertex
                    )
                )
            detected_track["landmarks"] = detected_people_landmarks
            detected_people.append(detected_track)

    return detected_people


def main():
    parser = argparse.ArgumentParser(description="Accept arguments with values")
    # Add an optional argument.
    parser.add_argument("--gcs_uri", help="Google Cloud Storage URI path", type=str)
    parser.add_argument("--api_timeout", help="Google Cloud Video Intelligence API request timeout in seconds",
                        type=int)
    parser.add_argument("--alarm_status", help="Is Alarm armed? Value: [armed, disarmed]", type=str)
    args = parser.parse_args()
    if args.gcs_uri:
        gcs_uri = args.gcs_uri
    else:
        print('Failed to obtain Google Cloud Storage URI path such as gs://bucket/video.mp4')
        exit(1)
    if args.api_timeout:
        timeout = args.api_timeout
    else:
        timeout = 300
    if args.alarm_status:
        is_alarm_armed = args.alarm_status == 'armed'
    else:
        is_alarm_armed = False

    results = detect_people(gcs_uri=gcs_uri, timeout=timeout)

    print('human detection returned results:')
    if not results:
        msg = "No humans detected"
        print(msg)
        logger.log_text(msg, severity=LOG_SEVERITY_NOTICE)
    else:
        print(results)
        if is_alarm_armed:
            logger.log_struct({
                'is_alarm_armed': is_alarm_armed,
                'human_detection_outcome': results,
            }, severity=LOG_SEVERITY_WARNING)
        else:
            logger.log_struct({
                'is_alarm_armed': is_alarm_armed,
                'human_detection_outcome': results,
            }, severity=LOG_SEVERITY_NOTICE)


if __name__ == "__main__":
    main()

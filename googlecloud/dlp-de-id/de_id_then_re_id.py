# Copyright 2021 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


def deidentify_with_fpe(
        project,
        input_str,
        info_types,
        alphabet=None,
        surrogate_type=None,
        key_name=None,
        wrapped_key=None,
):
    """Uses the Data Loss Prevention API to deidentify sensitive data in a
    string using Format Preserving Encryption (FPE).
    Args:
        project: The Google Cloud project id to use as a parent resource.
        input_str: The string to deidentify (will be treated as text).
        alphabet: The set of characters to replace sensitive ones with. For
            more information, see https://cloud.google.com/dlp/docs/reference/
            rest/v2beta2/organizations.deidentifyTemplates#ffxcommonnativealphabet
        surrogate_type: The name of the surrogate custom info type to use. Only
            necessary if you want to reverse the deidentification process. Can
            be essentially any arbitrary string, as long as it doesn't appear
            in your dataset otherwise.
        key_name: The name of the Cloud KMS key used to encrypt ('wrap') the
            AES-256 key. Example:
            key_name = 'projects/YOUR_GCLOUD_PROJECT/locations/YOUR_LOCATION/
            keyRings/YOUR_KEYRING_NAME/cryptoKeys/YOUR_KEY_NAME'
        wrapped_key: The encrypted ('wrapped') AES-256 key to use. This key
            should be encrypted using the Cloud KMS key specified by key_name.
    Returns:
        None; the response from the API is printed to the terminal.
    """
    import google.cloud.dlp
    dlp = google.cloud.dlp_v2.DlpServiceClient()
    # Convert the project id into a full resource id.
    parent = f"projects/{project}"
    # The wrapped key is base64-encoded, but the library expects a binary string, so decode it here.
    import base64
    wrapped_key = base64.b64decode(wrapped_key)

    crypto_replace_ffx_fpe_config = {
        "crypto_key": {
            "kms_wrapped": {"wrapped_key": wrapped_key, "crypto_key_name": key_name}
        },
        "common_alphabet": alphabet,
    }

    # surrogate type is the prefix in the Pseudonymized string
    if surrogate_type:
        crypto_replace_ffx_fpe_config["surrogate_info_type"] = {"name": surrogate_type}

    inspect_config = {"info_types": [{"name": info_type} for info_type in info_types]}
    deidentify_config = {
        "info_type_transformations": {
            "transformations": [
                {
                    "primitive_transformation": {
                        "crypto_replace_ffx_fpe_config": crypto_replace_ffx_fpe_config
                    }
                }
            ]
        }
    }

    item = {"value": input_str}
    # Call the DLP API https://cloud.google.com/dlp/docs/pseudonymization
    response = dlp.deidentify_content(
        request={
            "parent": parent,
            "deidentify_config": deidentify_config,
            "inspect_config": inspect_config,
            "item": item,
        }
    )

    return response.item.value


def deidentify_with_deterministic(
        project,
        input_str,
        info_types,
        surrogate_type=None,
        key_name=None,
        wrapped_key=None,
):
    """Uses the Data Loss Prevention API to deidentify sensitive data in a
    string using Deterministic encryption
    Args:
        project: The Google Cloud project id to use as a parent resource.
        input_str: The string to deidentify (will be treated as text).
        surrogate_type: The name of the surrogate custom info type to use. Only
            necessary if you want to reverse the deidentification process. Can
            be essentially any arbitrary string, as long as it doesn't appear
            in your dataset otherwise.
        key_name: The name of the Cloud KMS key used to encrypt ('wrap') the
            AES-256 key. Example:
            key_name = 'projects/YOUR_GCLOUD_PROJECT/locations/YOUR_LOCATION/
            keyRings/YOUR_KEYRING_NAME/cryptoKeys/YOUR_KEY_NAME'
        wrapped_key: The encrypted ('wrapped') AES-256 key to use. This key
            should be encrypted using the Cloud KMS key specified by key_name.
    Returns:
        None; the response from the API is printed to the terminal.
    """
    import google.cloud.dlp
    dlp = google.cloud.dlp_v2.DlpServiceClient()
    # Convert the project id into a full resource id.
    parent = f"projects/{project}"
    # The wrapped key is base64-encoded, but the library expects a binary string, so decode it here.
    import base64
    wrapped_key = base64.b64decode(wrapped_key)

    crypto_replace_deterministic_config = {
        "crypto_key": {
            "kms_wrapped": {"wrapped_key": wrapped_key, "crypto_key_name": key_name}
        },
    }

    # surrogate type is the prefix in the Pseudonymized string
    if surrogate_type:
        crypto_replace_deterministic_config["surrogate_info_type"] = {"name": surrogate_type}

    inspect_config = {"info_types": [{"name": info_type} for info_type in info_types]}
    deidentify_config = {
        "info_type_transformations": {
            "transformations": [
                {
                    "primitive_transformation": {
                        "crypto_deterministic_config": crypto_replace_deterministic_config
                    }
                }
            ]
        }
    }

    item = {"value": input_str}
    # Call the DLP API https://cloud.google.com/dlp/docs/pseudonymization
    response = dlp.deidentify_content(
        request={
            "parent": parent,
            "deidentify_config": deidentify_config,
            "inspect_config": inspect_config,
            "item": item,
        }
    )

    return response.item.value


def reidentify_with_fpe(
        project,
        input_str,
        alphabet=None,
        surrogate_type=None,
        key_name=None,
        wrapped_key=None,
):
    """Uses the Data Loss Prevention API to reidentify sensitive data in a
    string that was encrypted by Format Preserving Encryption (FPE).
    Args:
        project: The Google Cloud project id to use as a parent resource.
        input_str: The string to deidentify (will be treated as text).
        surrogate_type: The name of the surrogate custom info type to used
            during the encryption process.
        key_name: The name of the Cloud KMS key used to encrypt ('wrap') the
            AES-256 key. Example:
            keyName = 'projects/YOUR_GCLOUD_PROJECT/locations/YOUR_LOCATION/
            keyRings/YOUR_KEYRING_NAME/cryptoKeys/YOUR_KEY_NAME'
        wrapped_key: The encrypted ('wrapped') AES-256 key to use. This key
            should be encrypted using the Cloud KMS key specified by key_name.
    Returns:
        None; the response from the API is printed to the terminal.
    """
    import google.cloud.dlp
    dlp = google.cloud.dlp_v2.DlpServiceClient()
    # Convert the project id into a full resource id.
    parent = f"projects/{project}"
    # The wrapped key is base64-encoded, but the library expects a binary string, so decode it here.
    import base64
    wrapped_key = base64.b64decode(wrapped_key)

    reidentify_config = {
        "info_type_transformations": {
            "transformations": [
                {
                    "primitive_transformation": {
                        "crypto_replace_ffx_fpe_config": {
                            "crypto_key": {
                                "kms_wrapped": {
                                    "wrapped_key": wrapped_key,
                                    "crypto_key_name": key_name,
                                }
                            },
                            "common_alphabet": alphabet,
                            "surrogate_info_type": {"name": surrogate_type},
                        }
                    }
                }
            ]
        }
    }

    inspect_config = {
        "custom_info_types": [
            {"info_type": {"name": surrogate_type}, "surrogate_type": {}}
        ]
    }

    item = {"value": input_str}
    # Call the DLP API https://cloud.google.com/dlp/docs/pseudonymization
    response = dlp.reidentify_content(
        request={
            "parent": parent,
            "reidentify_config": reidentify_config,
            "inspect_config": inspect_config,
            "item": item,
        }
    )

    return response.item.value


def reidentify_with_deterministic(
        project,
        input_str,
        surrogate_type=None,
        key_name=None,
        wrapped_key=None,
):
    """Uses the Data Loss Prevention API to reidentify sensitive data in a
    string that was encrypted by Deterministic encryption.
    Args:
        project: The Google Cloud project id to use as a parent resource.
        input_str: The string to deidentify (will be treated as text).
        surrogate_type: The name of the surrogate custom info type to used
            during the encryption process.
        key_name: The name of the Cloud KMS key used to encrypt ('wrap') the
            AES-256 key. Example:
            keyName = 'projects/YOUR_GCLOUD_PROJECT/locations/YOUR_LOCATION/
            keyRings/YOUR_KEYRING_NAME/cryptoKeys/YOUR_KEY_NAME'
        wrapped_key: The encrypted ('wrapped') AES-256 key to use. This key
            should be encrypted using the Cloud KMS key specified by key_name.
    Returns:
        None; the response from the API is printed to the terminal.
    """
    import google.cloud.dlp
    dlp = google.cloud.dlp_v2.DlpServiceClient()
    # Convert the project id into a full resource id.
    parent = f"projects/{project}"
    # The wrapped key is base64-encoded, but the library expects a binary string, so decode it here.
    import base64
    wrapped_key = base64.b64decode(wrapped_key)

    reidentify_config = {
        "info_type_transformations": {
            "transformations": [
                {
                    "primitive_transformation": {
                        "crypto_deterministic_config": {
                            "crypto_key": {
                                "kms_wrapped": {
                                    "wrapped_key": wrapped_key,
                                    "crypto_key_name": key_name,
                                }
                            },
                            "surrogate_info_type": {"name": surrogate_type},
                        }
                    }
                }
            ]
        }
    }

    inspect_config = {
        "custom_info_types": [
            {"info_type": {"name": surrogate_type}, "surrogate_type": {}}
        ]
    }

    item = {"value": input_str}
    # Call the DLP API https://cloud.google.com/dlp/docs/pseudonymization
    response = dlp.reidentify_content(
        request={
            "parent": parent,
            "reidentify_config": reidentify_config,
            "inspect_config": inspect_config,
            "item": item,
        }
    )

    return response.item.value

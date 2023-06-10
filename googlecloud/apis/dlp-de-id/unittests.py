# Copyright 2021 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import google.cloud.dlp_v2
import unittest
from de_id_then_re_id import deidentify_with_fpe, deidentify_with_deterministic, reidentify_with_fpe, \
    reidentify_with_deterministic


class DLP_tests(unittest.TestCase):

    # executed prior to each test
    def setUp(self):
        self.SSN = "372819127"
        self.PII_sample = f"My SSN is {self.SSN}"
        self.HARMLESS_STRING = "My favorite color is blue"
        self.GCLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")

        # the following command takes a AES 16 bit key and wrap it with a KMS software symmetric key
        # echo -ne abcdefghijklmnop | gcloud kms encrypt --key deid --keyring test --location global --plaintext-file=- --ciphertext-file wrapped.key && cat wrapped.key | base64
        self.WRAPPED_KEY = (
            "CiQA2OrUscSx94ftGmZjyMbOGI7bFB1nrApM0rZb/DcyT3Sy+zgSOQAAN+6rjmbtY5h3S/jGohZz"
            "A3Qh0lkGvDvNK9zp+f+3o10yfEbr6AQZlWDcL3Ra+f6pI1zQOGe0Cw=="
        )
        self.KEY_NAME = (
            # Protection level: Software
            # Purpose: Symmetric encrypt/decrypt
            # Default algorithm: Google symmetric key
            f"projects/{self.GCLOUD_PROJECT}/locations/global/keyRings/test/cryptoKeys/deid"
        )
        self.SURROGATE_TYPE = "SSN_TOKEN"

    # executed after each test
    def tearDown(self):
        pass

    def test_deidentify_with_fpe_uses_surrogate_info_types(self):
        self.fpe_deid_str = deidentify_with_fpe(
            self.GCLOUD_PROJECT,
            self.PII_sample,
            ["US_SOCIAL_SECURITY_NUMBER"],
            alphabet=google.cloud.dlp_v2.CharsToIgnore.CommonCharsToIgnore.ALPHA_LOWER_CASE,
            wrapped_key=self.WRAPPED_KEY,
            key_name=self.KEY_NAME,
            surrogate_type=self.SURROGATE_TYPE,
        )
        print(f"de-identified PII string from DLP crypto_replace_ffx_fpe_config is `{self.fpe_deid_str}`")
        self.assertNotIn(self.SSN, self.fpe_deid_str,
                         f"de-identified string `{self.fpe_deid_str}` still contains sensitive data")

    def test_deidentify_with_deterministic_uses_surrogate_info_types(self):
        self.deterministic_deid_str = deidentify_with_deterministic(
            self.GCLOUD_PROJECT,
            self.PII_sample,
            ["US_SOCIAL_SECURITY_NUMBER"],
            wrapped_key=self.WRAPPED_KEY,
            key_name=self.KEY_NAME,
            surrogate_type=self.SURROGATE_TYPE,
        )
        print(f"de-identified PII string from DLP crypto_deterministic_config is `{self.deterministic_deid_str}`")
        self.assertNotIn(self.SSN, self.deterministic_deid_str,
                         f"de-identified string `{self.deterministic_deid_str}` still contains sensitive data")

    def test_reidentify_with_fpe(self):
        self.test_deidentify_with_fpe_uses_surrogate_info_types()
        labeled_fpe_string = f"re-identified content is {self.fpe_deid_str}"

        reid_str = reidentify_with_fpe(
            self.GCLOUD_PROJECT,
            labeled_fpe_string,
            surrogate_type=self.SURROGATE_TYPE,
            wrapped_key=self.WRAPPED_KEY,
            key_name=self.KEY_NAME,
            alphabet=google.cloud.dlp_v2.CharsToIgnore.CommonCharsToIgnore.ALPHA_LOWER_CASE,
        )
        print(f"re-identified content from DLP crypto_replace_ffx_fpe_config is `{reid_str}`")
        self.assertIn(self.PII_sample, reid_str,
                      f"re-identified content `{reid_str}` fails to contain `{self.PII_sample}`")

    def test_reidentify_with_deterministic(self):
        self.test_deidentify_with_deterministic_uses_surrogate_info_types()
        labeled_fpe_string = f"re-identified content is {self.deterministic_deid_str}"

        reid_str = reidentify_with_deterministic(
            self.GCLOUD_PROJECT,
            labeled_fpe_string,
            surrogate_type=self.SURROGATE_TYPE,
            wrapped_key=self.WRAPPED_KEY,
            key_name=self.KEY_NAME,
        )
        print(f"re-identified content from DLP crypto_deterministic_config is `{reid_str}`")
        self.assertIn(self.PII_sample, reid_str,
                      f"re-identified content `{reid_str}` fails to contain `{self.PII_sample}`")


if __name__ == "__main__":
    unittest.main()

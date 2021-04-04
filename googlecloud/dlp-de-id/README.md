# Data loss prevention API example
Unit tests for [the DLP sensitive data de-identification and re-identification](https://cloud.google.com/dlp/docs/deidentify-sensitive-data#dlp_deidentify_replace-python) using Pseudonymization.
[The video in the article](https://cloud.google.com/dlp/docs/pseudonymization) shows 3 methods
where the 2 reversible methods are implemented in this folder. I contributed to the deterministic encryption
in [this pull request](https://github.com/googleapis/python-dlp/pull/119) from the part of the code here.

0. `CryptoReplaceFfxFpeConfig` preserves the format for backward compatibility. The de-identified string has the same length.
0. `CryptoDeterministicConfig` works best for new implementations where the de-identified string has a longer string in a different format.

## Getting started
### Prerequisites
0. [Google cloud SDK](https://cloud.google.com/bigtable/docs/installing-cloud-sdk) install on localhost
0. Google data loss prevention API enabled. Create a service account and bind DLP User IAM role.
0. With service account key admin role, generate a .json key and store it somewhere at $HOME on local disk. 
0. Create a [Cloud KMS symmetric key](https://cloud.google.com/kms/docs/creating-keys)
0. Bind Cloud KMS CryptoKey Encrypter/Decrypter role to the developer's Google account under the key's IAM permissions tab.

### Create a wrapped key from AES 16 bit raw key
Authenticate the user to the gcloud command. Modify the environment variables per the key ring, key created. 
```shell
gcloud auth application-default login
gcloud auth login
RAW_KEY=abcdefghijklmnop
KEY_RING_NAME=test
KEY_NAME=deid
echo -ne $RAW_KEY | gcloud kms encrypt --key $KEY_NAME --keyring $KEY_RING_NAME --location global --plaintext-file=- --ciphertext-file wrapped.key && cat wrapped.key | base64
```
The output from the command above is the wrapped key which is base 64 decoded and passed to Cloud DLP. 

## setting up Pycharm
Download and install the lates PyCharm community edition. Open the current path and configure a python virtual environment.
The command to create a python virtual environment is `python3 -m venv . && . bin/activate && pip3 install -r requirements.txt` 
### Update the source with the wrapped key
```python
WRAPPED_KEY = (
            "CiQA2OrUscSx94ftGmZjyMbOGI7bFB1nrApM0rZb/DcyT3Sy+zgSOQAAN+6rjmbtY5h3S/jGohZz"
            "A3Qh0lkGvDvNK9zp+f+3o10yfEbr6AQZlWDcL3Ra+f6pI1zQOGe0Cw=="
KEY_NAME = (
            f"projects/{self.GCLOUD_PROJECT}/locations/global/keyRings/test/cryptoKeys/deid"
        )
```
### Environment variables
Right click on the class in unittests.py, select Debug. Observe errors and a Run/debug configuration created.
Add 2 environment variables to the configuration:

* GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json
* GOOGLE_CLOUD_PROJECT=PROJECT_ID 

## Executing tests
The unit tests output should look similar to the following:
* de-identified PII string from DLP crypto_deterministic_config is `My SSN is SSN_TOKEN(36):AcZdGwtYBAJSjm5CS520D9qTgWD+7v/6Mpo=`
* de-identified PII string from DLP crypto_replace_ffx_fpe_config is `My SSN is SSN_TOKEN(9):7I9OBJFOZ`
* re-identified content from DLP crypto_deterministic_config is `re-identified content is My SSN is 372819127`
* re-identified content from DLP crypto_replace_ffx_fpe_config is `re-identified content is My SSN is 372819127`
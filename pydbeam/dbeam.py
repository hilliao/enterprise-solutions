# Python3 wrapper for running DBeam project at https://github.com/hilliao/dbeam. The wrapper's purpose is to
# 1. get the database password from HashiCorp Vault, pass it to DBeam or form the SQL Query
# 2. use environment variables and defined variables to form SQL query
# --define-from-env=HOME --define a=b  --connectionUrl=jdbc:mysql://localhost:3306/dbeamtest --username=hil \
# --password=password --sqlFile=/Users/hil/tmp/pet.sql --output=/Users/hil/Documents/dbeampytest-mysql \
# --define-from-env=LANG --define c=d --define LDATE=20180530 --define foo=bar --define-from-vault=cbs_pii_db \
# --project=mock --zone=mock

import argparse
import subprocess
import os

# mock Hashicorp Vault secrets
mock_vault_dict = {
    'cbs_pii_db': {
        'enc_key': 'mysupersecretenckey',
        'jdbc_url': 'jdbc:mysql://mysqlserver:3306/cbs',
    },
    'cbs_pii_db2': {
        'foo': 'bar',
    }
}

# mock test SQL template
sql_template = '''select userid,aboutme,accountstatus,
 cast(AES_DECRYPT(unhex(address_city),'{vault[cbs_pii_db][enc_key]}') as CHAR) address_city,
 cast(AES_DECRYPT(unhex(address_country),'{vault[cbs_pii_db][enc_key]}') as CHAR) address_country,
 cast(AES_DECRYPT(unhex(address_state),'{vault[cbs_pii_db][enc_key]}') as CHAR) address_state,
 cast(AES_DECRYPT(unhex(address_street),'{vault[cbs_pii_db][enc_key]}') as CHAR) address_street,
 cast(AES_DECRYPT(unhex(address_zipcode),'{vault[cbs_pii_db][enc_key]}') as CHAR) address_zipcode,
 cast(AES_DECRYPT(unhex(homephonenumber),'{vault[cbs_pii_db][enc_key]}') as CHAR) homephonenumber,
 communityscore,createddate,
 cast(AES_DECRYPT(unhex(email),'{vault[cbs_pii_db][enc_key]}') as CHAR) email,
 cast(AES_DECRYPT(unhex(firstname),'{vault[cbs_pii_db][enc_key]}') as CHAR) firstname,
 gender,
 cast(AES_DECRYPT(unhex(lastname),'{vault[cbs_pii_db][enc_key]}') as CHAR) lastname,
 looklike,password,role,updateddate,username,
 website,lastpingdate,facebookid,lastfrdate,displayname,
 primaryphotopath,fromfacebook,activitytype,dateadded,
 cast(AES_DECRYPT(unhex(birthday_year),'{vault[cbs_pii_db][enc_key]}') as CHAR) birthday_year,
 cast(AES_DECRYPT(unhex(birthday_month),'{vault[cbs_pii_db][enc_key]}') as CHAR) birthday_month,
 cast(AES_DECRYPT(unhex(birthday_day),'{vault[cbs_pii_db][enc_key]}') as CHAR) birthday_day,
 encryption_level
from user u
where encryption_level = 1  and
      updateddate >= DATE_SUB('{env[DW_LDATE]}' ,INTERVAL 2 DAY)'''


def parse():
    parser = argparse.ArgumentParser()

    # DBeam parameters
    parser.add_argument('--project', help='Google Cloud Platform project for the Cloud Dataflow Runner')
    parser.add_argument('--zone', help='Google Cloud Platform zone for the Cloud Dataflow Runner')
    parser.add_argument('--output', required=True, help='output Google Cloud Storage path')
    parser.add_argument('--sqlFile', required=True, help='SQL template file location')
    parser.add_argument('--connectionUrl', required=True, help='database connection string')
    parser.add_argument('--username', required=False, help='username in database credentials')
    parser.add_argument('--password', metavar="VAULT_PATH",
                        help='HashiCorp Vault path to query the database password, e,g, secret/foo')

    # parameters to generate SQL query for --sqlFile, database password for --password
    parser.add_argument('--define', type=kv_var, default=list(), action='append',
                        help="Define parameter variables for SQL template string replacement. Example: --define LDATE=20180530 --define foo=bar")
    parser.add_argument('--define-from-env', type=env_key, default=list(), action='append',
                        help="Use a environment variable for SQL template string replacement", required=False)
    parser.add_argument('--define-from-vault', type=dict_key, default=list(), action='append')

    return parser.parse_args()


def dict_key(s):
    # todo implement with client.read('secret/foo') per https://github.com/ianunruh/hvac
    return s, mock_vault_dict[s]


def kv_var(s):
    nv = s.split('=', 1)
    if len(nv) == 1:
        raise ValueError('--define argument had no "=" in string')
    return tuple(nv)


def env_key(s):
    return s, os.environ.get(s)


def main():
    args = parse()

    # print debugging information
    print('args.define: ' + str(args.define))
    print('args.define_from_env: ' + str(args.define_from_env))
    print('args.define_from_vault: ' + str(args.define_from_vault))

    dbeam(args.connectionUrl, args.username, args.password, args.sqlFile, args.output, args.project, args.zone)


def dbeam(connectionUrl, username, password, sql_file, output, project=None, zone=None):
    dbeam_path_list = ["/Users/hil/cbsi/dbeam", "/usr/lib/dbeam"]
    dbeam_path = [p for p in dbeam_path_list if os.path.isdir(p)]
    if len(dbeam_path) == 0:
        raise FileNotFoundError("Failed to locate DBeam's directory in " + str(dbeam_path_list))

    dbeam_path = dbeam_path[0]

    if project is None:
        # DirectRunner
        cmd = [os.path.join(dbeam_path, "dbeam-pack/target/pack/bin/jdbc-avro-job")]
        cmd.append("--connectionUrl=" + connectionUrl)
        cmd.append("--username=" + username)
        cmd.append("--password=" + password)
        cmd.append("--sqlFile=" + sql_file)
        cmd.append("--output=" + output)
        dbeam_proc = subprocess.run(cmd, shell=False, check=True)
    else:
        if zone is None:
            raise ValueError("--zone needs to exist and be a valid Google Cloud Platform zone")

        sbt_path_list = ["/usr/local/bin/sbt", "/usr/bin/sbt"]
        sbt_path = [p for p in sbt_path_list if os.path.exists(p)]
        if len(sbt_path) == 0:
            raise FileNotFoundError("sbt command not found in " + str(sbt_path_list))
        sbt_path = sbt_path[0]

        # Google Cloud DataflowRunner
        cmd = [sbt_path, "project dbeamCore", "runMain com.spotify.dbeam.JdbcAvroJob --project={0} \
        --zone={1} --runner=DataflowRunner --connectionUrl={2} --sqlFile={3} --username={4} --password={5} --output={6}"
            .format(project, zone, connectionUrl, sql_file, username, password, output)]
        dbeam_proc = subprocess.run(cmd, cwd=dbeam_path, shell=False, check=True)


if __name__ == "__main__":
    main()

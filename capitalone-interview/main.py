import urllib3
import json

const_avg = 'average'

const_months = 'months'

const_income = 'income'

const_spent = 'spent'


def get_all_transactions_from_url(url):
    http = urllib3.PoolManager()
    encoded_body = json.dumps({"args": {"uid": 1110590645,
                                        "token": "73266BBBE75AEF77972F1535912990CA",
                                        "api-token": "AppTokenForInterview",
                                        "json-strict-mode": False,
                                        "json-verbose-response": False}
                               })

    response = http.request('POST', url,
                            headers={'Content-Type': 'application/json'},
                            body=encoded_body)

    if response.status != 200:
        return "Error with HTTP status: " + response.status

    return json.loads(response.data.decode('utf8'))


def get_transactions_by_month(json_transactions):
    trans = json_transactions['transactions']

    '''get a list of months for all transactions'''
    by_month = set([t['transaction-time'][:7] for t in trans])
    by_month = list(by_month)
    by_month.sort()

    '''spending aggregation for each month'''
    month_spent = {}
    month_income = {}
    for m in by_month:
        month_spent[m] = [int(t['amount']) for t in trans if t['transaction-time'].startswith(m)
                          and t['is-pending'] == False
                          and int(t['amount']) < 0
                          ]

        month_income[m] = [int(t['amount']) for t in trans if t['transaction-time'].startswith(m)
                           and t['is-pending'] == False
                           and int(t['amount']) > 0
                           ]

        num_base = 10000.0
        month_spent[m] = float(sum(month_spent[m]) * -1) / num_base
        month_income[m] = float(sum(month_income[m])) / num_base

    return {const_spent: month_spent, const_income: month_income, const_months: by_month}


def get_average_month(transactions):
    sorted_trans_months = sorted(transactions, key=transactions.__getitem__)
    mid = int(len(sorted_trans_months) / 2)
    average_amount = transactions[sorted_trans_months[mid]]

    return average_amount


def main():
    url = 'https://2016.api.levelmoney.com/api/v2/core/get-all-transactions'
    all_trans = get_all_transactions_from_url(url)
    monthly_trans = get_transactions_by_month(all_trans)
    monthly_trans[const_spent][const_avg] = get_average_month(monthly_trans[const_spent])
    monthly_trans[const_income][const_avg] = get_average_month(monthly_trans[const_income])
    monthly_trans[const_months].append(const_avg)

    for m in monthly_trans[const_months]:
        print(m + " -> spent: $" + str(monthly_trans[const_spent][m])
              + ", income: $" + str(monthly_trans[const_income][m]))


main()

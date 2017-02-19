/usr/bin/python3.5 /home/hil/github/PlayTest/capitalone-interview/main.py
2014-10 -> spent: $1578.44, income: $3429.79
2014-11 -> spent: $4625.67, income: $3949.51
2014-12 -> spent: $4785.78, income: $3954.32
2015-01 -> spent: $3811.42, income: $3925.98
2015-02 -> spent: $4217.99, income: $3936.64
2015-03 -> spent: $3460.17, income: $3942.73
2015-04 -> spent: $2985.45, income: $3943.68
2015-05 -> spent: $2692.67, income: $3416.4
2015-06 -> spent: $3758.45, income: $3918.23
2015-07 -> spent: $3921.05, income: $3917.18
2015-08 -> spent: $2809.03, income: $3384.88
2015-09 -> spent: $3055.51, income: $3922.72
2015-10 -> spent: $3301.84, income: $1717.43
2015-11 -> spent: $3154.04, income: $3977.78
2015-12 -> spent: $3208.54, income: $1725.57
2016-01 -> spent: $2827.81, income: $2242.89
2016-02 -> spent: $3118.91, income: $3451.38
2016-03 -> spent: $4216.55, income: $3386.61
2016-04 -> spent: $3912.18, income: $3917.4
2016-05 -> spent: $3543.46, income: $3991.18
2016-06 -> spent: $3276.24, income: $3927.78
2016-07 -> spent: $3262.42, income: $3928.23
2016-08 -> spent: $3072.53, income: $3922.33
2016-09 -> spent: $3720.2, income: $2229.63
2016-10 -> spent: $3273.58, income: $2209.91
2016-11 -> spent: $4831.32, income: $3441.83
2016-12 -> spent: $3106.19, income: $3966.25
2017-01 -> spent: $4119.53, income: $3486.48
2017-02 -> spent: $2935.51, income: $0.0
average -> spent: $3276.24, income: $3917.4


/usr/bin/python3.5 /home/hil/github/PlayTest/capitalone-interview/main.py --ignore-donuts
2014-10 -> spent: $1494.16, income: $3429.79
2014-11 -> spent: $4591.11, income: $3949.51
2014-12 -> spent: $4690.32, income: $3954.32
2015-01 -> spent: $3756.73, income: $3925.98
2015-02 -> spent: $4159.2, income: $3936.64
2015-03 -> spent: $3392.36, income: $3942.73
2015-04 -> spent: $2939.79, income: $3943.68
2015-05 -> spent: $2670.56, income: $3416.4
2015-06 -> spent: $3724.28, income: $3918.23
2015-07 -> spent: $3898.14, income: $3917.18
2015-08 -> spent: $2787.39, income: $3384.88
2015-09 -> spent: $3036.03, income: $3922.72
2015-10 -> spent: $3301.84, income: $1717.43
2015-11 -> spent: $3135.03, income: $3977.78
2015-12 -> spent: $3185.28, income: $1725.57
2016-01 -> spent: $2746.04, income: $2242.89
2016-02 -> spent: $3082.69, income: $3451.38
2016-03 -> spent: $4207.85, income: $3386.61
2016-04 -> spent: $3904.39, income: $3917.4
2016-05 -> spent: $3505.4, income: $3991.18
2016-06 -> spent: $3222.02, income: $3927.78
2016-07 -> spent: $3202.71, income: $3928.23
2016-08 -> spent: $3015.28, income: $3922.33
2016-09 -> spent: $3677.15, income: $2229.63
2016-10 -> spent: $3240.28, income: $2209.91
2016-11 -> spent: $4798.46, income: $3441.83
2016-12 -> spent: $3078.46, income: $3966.25
2017-01 -> spent: $4027.46, income: $3486.48
2017-02 -> spent: $2928.72, income: $0.0
average -> spent: $3240.28, income: $3917.4



Coding Exercise Instructions:

Our API is documented at https://doc.level-labs.com - username: interview@levelmoney.com password: password2. We'd like you to write a program that:
·         Loads a user's transactions from the GetAllTransactions endpoint
·         Determines how much money the user spends and makes in each of the months for which we have data, and in the "average" month. What "average" means is up to you.
·         Output these numbers in the following format (and optionally in a more pretty format, if you see fit)
{"2014-10": {"spent": "$200.00", "income": "$500.00"},
"2014-11": {"spent": "$1510.05", "income": "$1000.00"},
...
"2015-04": {"spent": "$300.00", "income": "$500.00"},
"average": {"spent": "$750.00", "income": "$950.00"}}
You have considerable latitude on how to display this data, obtain it, and what language to use. Please do this in the way that feels most comfortable for you. For many of our applicants, they prefer to use a script you run from the command line. For some, it is a webpage that displays things. For others, it’s a live code notebook. What’s important is that it is reproducible by us.
We’d also like you to try and add at least one “additional feature” to this program (and if you’re able, all of them). They’re listed below as command line switches for a terminal program, but we’d accept any method that lets a user decide how to display this data.
·         --ignore-donuts: The user is so enthusiastic about donuts that they don't want donut spending to come out of their budget. Disregard all donut-related transactions from the spending. You can just use the merchant field to determine what's a donut - donut transactions will be named “Krispy Kreme Donuts” or “DUNKIN #336784”.
·         --crystal-ball: We expose a GetProjectedTransactionsForMonth endpoint, which returns all the transactions that have happened or are expected to happen for a given month. It looks like right now it only works for this month, but that's OK. Merge the results of this API call with the full list from GetAllTransactions and use it to generate predicted spending and income numbers for the rest of this month, in addition to previous months.
·         --ignore-cc-payments: Paying off a credit card shows up as a credit transaction and a debit transaction, but it's not really "spending" or "income". Make your aggregate numbers disregard credit card payments. For the users we give you, credit card payments will consist of two transactions with opposite amounts (e.g. 5000000 centocents and -5000000 centocents) within 24 hours of each other. For verification, you should also output a list of the credit card payments you detected - this can be in whatever format you like.

We recommend using Github for source control and checking-in often as you work (even if this means the that not every ref in the branch you work on compiles). This gives us some insight into how you work, without us having to look over your shoulder every 5 minutes.

When you have completed the exercise, please upload your entire solution to Github.com if your code is not already there.  Then send an email with the URL of your repository to COFI_Coding_Exercise@capitalone.com  Please make sure you have an appropriate README documenting how we should compile (if necessary) and run your solution.

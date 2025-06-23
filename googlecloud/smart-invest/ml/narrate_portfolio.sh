#!/bin/bash

set -e
# This script demonstrates how to print key-value pairs from an associative array
# and dynamically fetch and display live stock quotes for each item.

# Declare an associative array
# Associative arrays require Bash 4 or later.
declare -A portfolio_dict

# Populate the associative array with example data.
# The stock symbols here will be used to fetch live quotes.
portfolio_dict["BRK.B"]="41"
portfolio_dict["DIS"]="232"
portfolio_dict["DOW"]="325"
portfolio_dict["EIDO"]="1065"
portfolio_dict["EWM"]="620"
portfolio_dict["INDA"]="702"
portfolio_dict["LMT"]="89"
portfolio_dict["MITSY"]="91"
portfolio_dict["NSRGY"]="3"
portfolio_dict["QQQ"]="3"
portfolio_dict["TSM"]="3"
portfolio_dict["UNH"]="50"
portfolio_dict["VNM"]="2013"
portfolio_dict["CASH"]="254058.95"

# Prerequisite: Ensure 'jq' is installed for JSON parsing.
# You can install it using: sudo apt-get install jq (Debian/Ubuntu)

# Export the authentication token for the API call once.
export TOKEN=$(gcloud auth print-identity-token)

# Build a comma-separated string of all stock tickers from the portfolio_dict.
tickers_query=""
for ticker in "${!portfolio_dict[@]}"; do
    if [[ "$ticker" != "CASH" ]]; then
        if [[ -z "$tickers_query" ]]; then
            tickers_query="$ticker"
        else
            tickers_query="${tickers_query},${ticker}"
        fi
    fi
done

# Execute the cURL command only once with the concatenated tickers.
# Store the full JSON response.
stock_quotes_json=$(curl --silent --location "https://us-west1-hil-financial-services.cloudfunctions.net/stock-quotes/?tickers=${tickers_query}" \
--header "Authorization: Bearer $TOKEN")


total_market_value=0
declare -A portfolio_holdings
# Iterate over the keys (stock tickers) of the associative array.
for item_string in "${!portfolio_dict[@]}"; do
    # Get the corresponding number of shares for the current item.
    item_number="${portfolio_dict[$item_string]}"

    # Check if the current item is a stock ticker (not "CASH") and if the API call was successful.
    if [[ "$item_string" != "CASH" ]]; then
        # Check if the overall curl command was successful and returned JSON.
        if [ $? -eq 0 ] && [ -n "$stock_quotes_json" ]; then
            # Parse the already fetched JSON response using jq to extract the 'Last' value for the current ticker.
            # Handle cases where the ticker might not be found in the API response.
            last_value=$(echo "$stock_quotes_json" | jq -r --arg ticker "$item_string" '.[$ticker].Last // empty')

            # Print the last value.
            if [[ -n "$last_value" ]]; then
                market_value=$(awk "BEGIN {printf \"%.2f\", $item_number * $last_value}")
                total_market_value=$(awk "BEGIN {printf \"%.2f\", $total_market_value + $market_value}")
                portfolio_holdings["$item_string"]=" Last value for $item_string: $last_value. Market Value: $market_value"
            else
                portfolio_holdings["$item_string"]=" Last value for $item_string: N/A. Market Value: N/A"
            fi
        else
            portfolio_holdings["$item_string"]=" Failed to process live quote for $item_string. API response was not valid or empty."
            portfolio_holdings["${item_string}_error"]=" Please ensure 'jq' is installed, your 'gcloud' token is valid, and you have network connectivity."
            # Optionally, uncomment the line below for more detailed debugging:
            # echo "  Raw Response for $item_string: $stock_quotes_json"
        fi
    else
        portfolio_holdings["$item_string"]=" Last value for CASH: 1. Market Value: $item_number"
        total_market_value=$(awk "BEGIN {printf \"%.2f\", $total_market_value + $item_number}")
    fi
done

# Now, iterate again to print the percentage allocation for each item.
for item_string in "${!portfolio_dict[@]}"; do
    item_number="${portfolio_dict[$item_string]}"

    echo -n "${item_string}: ${item_number} shares."
    echo -n "${portfolio_holdings[$item_string]}."
    if [[ "$item_string" != "CASH" ]]; then
        if [ $? -eq 0 ] && [ -n "$stock_quotes_json" ]; then
            last_value=$(echo "$stock_quotes_json" | jq -r --arg ticker "$item_string" '.[$ticker].Last // empty')
            if [[ -n "$last_value" ]]; then
                market_value=$(awk "BEGIN {printf \"%.2f\", $item_number * $last_value}")
                if (( $(echo "$total_market_value > 0" | bc -l) )); then
                    percentage=$(awk "BEGIN {printf \"%.2f\", ($market_value / $total_market_value) * 100}")
                    echo " Allocation: ${percentage}%"
                else
                    echo " Allocation: 0.00% (Total market value is zero)"
                fi
            fi
        fi
    else
        percentage=$(awk "BEGIN {printf \"%.2f\", ($item_number / $total_market_value) * 100}")
        echo " Allocation: ${percentage}%"
    fi
done
# How to run this script:
# 1. Save the content to a file, e.g., `narrate_portfolio.sh`.
# 2. Make it executable: `chmod +x narrate_portfolio.sh`
# 3. Run it from your terminal: `./narrate_portfolio.sh`

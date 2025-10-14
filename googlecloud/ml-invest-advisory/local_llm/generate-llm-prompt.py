# SET GOOGLE_APPLICATION_CREDENTIALS environment variable
# https://cloud.google.com/docs/authentication/application-default-credentials

import argparse
import os
import json
import sys

import google.auth.transport.requests
import requests
from google.oauth2 import id_token


def invoke_cloud_run(base_url: str, url: str) -> str:
    """
    Invokes a Cloud Run endpoint that requires authentication.

    This function automatically uses the service account credentials from the
    environment variable `GOOGLE_APPLICATION_CREDENTIALS` to authenticate
    against a Cloud Run endpoint.
    GOOGLE_APPLICATION_CREDENTIALS environment variable to generate an
    ID token for the request.

    Args:
        base_url (str): The URL of the Cloud Run endpoint visible in Google Cloud Console.
        url (str): The full URL of the Cloud Run endpoint to invoke.


    Returns:
        str: The text content of the response if successful.

    Raises:
        Exception: If the HTTP request fails.
    """
    try:
        # The 'audience' for an ID token is the URL of the service being called.
        # This is a security measure to ensure the token is only used for this service.
        audience = base_url

        print(f"Authenticating for audience: {audience}")

        # Fetch the ID token using Application Default Credentials
        auth_req = google.auth.transport.requests.Request()
        identity_token = id_token.fetch_id_token(auth_req, audience)

        # Create the Authorization header
        headers = {
            "Authorization": f"Bearer {identity_token}"
        }

        print(f"Successfully obtained ID token. Making request at {url}")

        # Make the authenticated GET request
        response = requests.get(url, headers=headers)

        # Raise an exception for bad status codes (4xx or 5xx)
        response.raise_for_status()

        return response.text

    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        raise


def merge_portfolio_dict(portfolio_holdings: dict, stock_quotes: dict) -> dict:
    """
    Merges portfolio units into a dictionary of stock quotes.

    This function creates a deep copy of the stock_quotes to avoid
    modifying the original data structure.

    Args:
        portfolio_holdings (dict): A dictionary with tickers and their shares.        An example of the expected format is:
        {
            "AAAU": {"shares": 31.90},
            "QQQ": {"shares": 19.41},
            "NVDA": {"shares": 1},
            "GOOGL": {"shares": 3},
            "VOO": {"shares": 21.22}
        }

        stock_quotes (dict): A dictionary with tickers and detailed quote info.

    Returns:
        dict: A new dictionary containing the merged data.
    """
    # Create a deep copy of the quotes to avoid changing the original dict
    merged_json = json.loads(json.dumps(stock_quotes))

    # Loop through each ticker in the portfolio_units dictionary
    for ticker, share_count in portfolio_holdings.items():
        # Check if the ticker exists in our merged data
        if ticker in merged_json:
            # If it exists, update the nested dictionary with the units data
            merged_json[ticker].update(share_count)
        else:
            # If a ticker from portfolio_units is not in stock_quotes,
            # you could add it as a new entry.
            merged_json[ticker] = share_count

    return merged_json


def calculate_portfolio_1day_diff(portfolio_data: dict = None) -> dict:
    """
    Calculates current and previous values for portfolio holdings from a portfolio dict
    or a default string. It also computes the total portfolio value. The resulting dict
    has the attributes easily understood by LLM.

    Args:
        portfolio_data (dict, optional): A dictionary containing portfolio holdings.
                                        If None, uses a default data structure.
                                        Each key in the dict is a ticker symbol (str).
                                        Each value is a dict with the following required attributes:
                                        - "shares" (float): The number of shares held.
                                        - "Last" (float): The last traded price of the stock.
                                        - "PreviousClose" (float): The previous closing price of the stock.

    Returns:
        dict: A dictionary containing the calculated values for each ticker
              and a '__SUM' key with the total portfolio values.
    """
    if portfolio_data is None:
        default_json_string = """
        {
          "NVDA": {"shares": 10.90, "Last": "183.16", "PreviousClose": "192.1"},
          "QQQ": {"shares": 19.41, "Last": "589.93", "PreviousClose": "610.70001"},
          "VOO": {"shares": 21.22, "Last": "600.51", "PreviousClose": "617.09998"}
        }
        """
        portfolio_data = json.loads(default_json_string)  # Load default from string if no data provided

    result = {}
    total_current_value = 0.0
    total_previous_value = 0.0

    # Process each ticker in the portfolio
    for ticker, attributes in portfolio_data.items():
        try:
            share_count = float(attributes.get('shares', 0))
            last_price = float(attributes.get('Last', 0))
            previous_close = float(attributes.get('PreviousClose', 0))

            current_value = share_count * last_price
            previous_value = share_count * previous_close

            # Store results as floating point numbers, rounded to 2 decimal places
            result[ticker] = {
                'Current Value': round(current_value, 2),
                'Previous Value': round(previous_value, 2),
                'shares': share_count,
                'single share change in percentage': str(
                    round(float(attributes.get('NetChangePct', 0)) * 100, 2)) + '%',
            }

            # Add to the running totals
            total_current_value += current_value
            total_previous_value += previous_value

        except (ValueError, TypeError) as e:
            print(f"Skipping ticker {ticker} due to a data error: {e}", file=sys.stderr)
            result[ticker] = None

    # Add the '__SUM' key with the totals
    result['__SUM'] = {
        'Current Value': round(total_current_value, 2),
        'Previous Value': round(total_previous_value, 2),
        'daily performance change in percentage': str(
            round((total_current_value - total_previous_value) / total_previous_value * 100, 2)) + '%'
    }

    # Calculate the weight of each holding
    for ticker, attributes in result.items():
        if ticker != '__SUM':
            attributes['weight in percentage'] = attributes['weight in percentage'] = str(
                round(attributes['Current Value'] / result['__SUM']['Current Value'] * 100, 2)) + '%'

    return result


def load_portfolio_holding_file(file_path: str) -> dict:
    """
    Loads portfolio share units from a JSON file.

    Args:
        file_path (str): The path to the JSON file.

    Returns:
        dict: A dictionary containing the portfolio shares.
    """
    with open(file_path, 'r') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description='Process portfolio data.')
    parser.add_argument('--portfolio_file', type=str, required=True, help=
    'The path to the portfolio units JSON file. The file should be in the format: {"TICKER": {"Units": <number>}}')
    parser.add_argument('--llm_prompt_template', type=str, required=True, help=
    'The path to the LLM prompt template text file that contains {{PORTFOLIO_HOLDING_DATA_JSON}}.')
    args = parser.parse_args()

    portfolio_holdings = load_portfolio_holding_file(args.portfolio_file)

    # The URL of the Cloud Run function
    cloud_run_base_url = "https://us-central1-hil-financial-services.cloudfunctions.net/stock-quotes"
    if "STOCK_QUOTES_CLOUD_RUN_URL" in os.environ:
        cloud_run_base_url = os.environ["STOCK_QUOTES_CLOUD_RUN_URL"]
        print(f"Using STOCK_QUOTES_CLOUD_RUN_URL from environment variable: {cloud_run_base_url}")
    else:
        print(f"STOCK_QUOTES_CLOUD_RUN_URL environment variable not set. Using default: {cloud_run_base_url}")

    tickers = list(portfolio_holdings.keys())
    cloud_run_url = f"{cloud_run_base_url}/?tickers={','.join(tickers)}"

    # Ensure the environment variable is set before running
    if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ:
        print("Error: The GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.", file=sys.stderr)
        print("Please set it to the path of your service account key file.", file=sys.stderr)
        sys.exit(1)

    try:
        # Call the function and print the result
        result = invoke_cloud_run(cloud_run_base_url, cloud_run_url)
        print("\n--- Parsing response from Cloud Run service to JSON ---")
        num_lines_to_print = 10
        try:
            json_response = json.loads(result)
            print(f"--- Parsed JSON Response (top {num_lines_to_print} lines) ---")
            print('\n'.join(json.dumps(json_response, indent=2).splitlines()[:num_lines_to_print]))
        except json.JSONDecodeError:
            print("\n--- Response is not valid JSON ---")
            sys.exit(1)


    except Exception as e:
        print(f"\nFailed to invoke Cloud Run endpoint. Please check your URL and permissions.")
        sys.exit(1)

    portfolio_holdings_quotes = merge_portfolio_dict(portfolio_holdings, json_response)
    portfolio_holding_values = calculate_portfolio_1day_diff(        portfolio_holdings_quotes)
    num_lines_to_print = 15
    print(f"\n--- Portfolio value change from last trading day (top {num_lines_to_print} lines) ---")
    print('\n'.join(json.dumps(portfolio_holding_values, indent=2).splitlines()[:num_lines_to_print]))

    # Read the prompt template
    with open(args.llm_prompt_template, 'r') as f:
        prompt_template = f.read()

    # Replace the placeholder with the JSON data
    llm_ready_prompt = prompt_template.replace("{{PORTFOLIO_HOLDING_DATA_JSON}}",
                                               json.dumps(portfolio_holding_values, indent=2))

    # Write the final prompt to a file named prompt.txt in the same directory as the template
    output_file_path = os.path.join(os.path.dirname(args.llm_prompt_template), "prompt.txt")
    with open(output_file_path, 'w') as f:
        f.write(llm_ready_prompt)

    print(f"\nLLM prompt written to: {output_file_path}")


if __name__ == "__main__":
    main()

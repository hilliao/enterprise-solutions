# SET GOOGLE_APPLICATION_CREDENTIALS environment variable
# https://cloud.google.com/docs/authentication/application-default-credentials

import os
from textwrap import indent

import requests
import google.auth.transport.requests
from google.oauth2 import id_token


def invoke_cloud_run(base_url: str, url: str) -> str:
    """
    Invokes a Cloud Run endpoint that requires authentication.

    This function automatically uses the service account credentials from the
    GOOGLE_APPLICATION_CREDENTIALS environment variable to generate an
    ID token for the request.

    Args:
        base_url (str): The full URL of the Cloud Run endpoint to invoke.

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

        print("Successfully obtained ID token. Making request...")

        # Make the authenticated GET request
        response = requests.get(url, headers=headers)

        # Raise an exception for bad status codes (4xx or 5xx)
        response.raise_for_status()

        print("Request successful.")
        return response.text

    except Exception as e:
        print(f"An error occurred: {e}")
        raise


import json


def merge_portfolio_data(portfolio_units: dict, stock_quotes: dict) -> dict:
    """
    Merges portfolio units into a dictionary of stock quotes.

    This function creates a deep copy of the stock_quotes to avoid
    modifying the original data structure.

    Args:
        portfolio_units (dict): A dictionary with tickers and their units.
        stock_quotes (dict): A dictionary with tickers and detailed quote info.

    Returns:
        dict: A new dictionary containing the merged data.
    """
    # Create a deep copy of the quotes to avoid changing the original dict
    merged_data = json.loads(json.dumps(stock_quotes))

    # Loop through each ticker in the portfolio_units dictionary
    for ticker, units_data in portfolio_units.items():
        # Check if the ticker exists in our merged data
        if ticker in merged_data:
            # If it exists, update the nested dictionary with the units data
            merged_data[ticker].update(units_data)
        else:
            # If a ticker from portfolio_units is not in stock_quotes,
            # you could add it as a new entry.
            merged_data[ticker] = units_data

    return merged_data


def calculate_portfolio_values(portfolio_data: dict = None) -> dict:
    """
    Calculates current and previous values for portfolio holdings from a JSON file
    or a default string. It also computes the total portfolio value.

    Args:
        portfolio_data (dict, optional): A dictionary containing portfolio holdings.
                                        If None, uses a default data structure.

    Returns:
        dict: A dictionary containing the calculated values for each ticker
              and a '__SUM' key with the total portfolio values.
    """
    if portfolio_data is None:
        default_json_string = """
        {
          "NVDA": {"Units": 10.90, "Last": "183.16", "PreviousClose": "192.1"},
          "QQQ": {"Units": 19.41, "Last": "589.93", "PreviousClose": "610.70001"},
          "VOO": {"Units": 21.22, "Last": "600.51", "PreviousClose": "617.09998"}
        }
        """
        portfolio_data = json.loads(default_json_string)  # Load default from string if no data provided

    result = {}
    total_current_value = 0.0
    total_previous_value = 0.0

    # Process each ticker in the portfolio
    for ticker, attributes in portfolio_data.items():
        try:
            units = float(attributes.get('Units', 0))
            last_price = float(attributes.get('Last', 0))
            previous_close = float(attributes.get('PreviousClose', 0))

            current_value = units * last_price
            previous_value = units * previous_close

            # Store results as floating point numbers, rounded to 2 decimal places
            result[ticker] = {
                'CurrentValue': round(current_value, 2),
                'PreviousValue': round(previous_value, 2),
                'NetChangePct': str(round(float(attributes.get('NetChangePct', 0)) * 100, 2)) + '%',
            }

            # Add to the running totals
            total_current_value += current_value
            total_previous_value += previous_value

        except (ValueError, TypeError) as e:
            print(f"Skipping ticker {ticker} due to a data error: {e}")
            result[ticker] = {'CurrentValue': 0.0, 'PreviousValue': 0.0}

    # Add the '__SUM' key with the totals
    result['__SUM'] = {
        'CurrentValue': round(total_current_value, 2),
        'PreviousValue': round(total_previous_value, 2),
        'NetChangePct': str(round((total_current_value - total_previous_value) / total_previous_value * 100, 2)) + '%'
    }

    return result


# The URL of your Cloud Run function
cloud_run_url = "https://us-west1-hil-financial-services.cloudfunctions.net/stock-quotes/?tickers=VOO%2CGLD%2CQQQ"
cloud_run_base_url = "https://us-west1-hil-financial-services.cloudfunctions.net/stock-quotes"

# Ensure the environment variable is set before running
if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ:
    print("Error: The GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.")
    print("Please set it to the path of your service account key file.")
else:
    try:
        # Call the function and print the result
        result = invoke_cloud_run(cloud_run_base_url, cloud_run_url)
        print("\n--- Response from Cloud Run ---")
        import json

        try:
            json_response = json.loads(result)
            print("\n--- Parsed JSON Response ---")
            print(json.dumps(json_response, indent=2))
        except json.JSONDecodeError:
            print("\n--- Response is not valid JSON ---")

    except Exception as e:
        print(f"\nFailed to invoke Cloud Run endpoint. Please check your URL and permissions.")

    portfolio_units = {
        "GLD": {
            "Units": 31.90
        },
        "QQQ": {
            "Units": 19.41
        },
        "VOO": {
            "Units": 21.22
        }
    }

    merged_data = merge_portfolio_data(portfolio_units, json_response)
    print("\n--- Merged Data ---")
    print(json.dumps(merged_data, indent=2))
    portfolio_values = calculate_portfolio_values(merged_data) # Call the function with merged data
    print("\n--- Calculated Portfolio Values ---") # Add a descriptive header
    print(json.dumps(portfolio_values, indent=2)) # Use json.dumps for printing to console

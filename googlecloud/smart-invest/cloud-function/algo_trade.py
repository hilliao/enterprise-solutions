class Order:
    def __init__(self, shares: float, cash: float, price: float):
        self.shares = shares
        self.cash = cash
        self.price = price

    def to_dict(self):
        return {"shares": self.shares, "cash": self.cash, "price": self.price}


def recommend(amplify: float, intended_allocation: dict, quotes: dict):
    trades = {}

    for ticker in quotes:
        if isinstance(quotes[ticker], Exception):
            # assign the Exception to trade dictionary's value for later processing
            trades[ticker] = quotes[ticker]
            continue
        # Only the Yahoo Finance cached quotes have 50 and 200 day moving averages
        # If the cloud scheduler execution does not contain the stock ticker, the method would return None
        if not quotes[ticker].diff_price_average():
            # Make the return dict have values of Exceptions for later HTTP response
            trades[ticker] = Exception("Failed to get fiftyDayAverage or twoHundredDayAverage from cached quotes")
            continue

        cash = float(intended_allocation[ticker])

        # average of the moving averages minus the current stock price
        average_price_diff = -1 * quotes[ticker].diff_price_average()
        # how much more or less does the trader want to buy
        latest_ticker_price = quotes[ticker].latest_ticker_price()
        buy_adjust = average_price_diff / latest_ticker_price
        # how much cash does thr trader want to use
        adjusted_cash = (buy_adjust + 1) * cash
        # how many shares to buy
        buy_share_count = adjusted_cash / latest_ticker_price
        # 2 decimals max
        shares_count = round(max(buy_share_count * amplify, 0), 2)

        trades[ticker] = Order(shares=shares_count, cash=shares_count * latest_ticker_price, price=latest_ticker_price)

    return trades

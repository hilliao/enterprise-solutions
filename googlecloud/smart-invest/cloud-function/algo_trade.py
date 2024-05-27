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

        cash = float(intended_allocation[ticker])
        latest_ticker_price = quotes[ticker].latest_ticker_price()

        # Only the Yahoo Finance cached quotes have 50 and 200 day moving averages
        # If the cloud scheduler execution does not contain the stock ticker, don't adjust how many shares to buy
        if quotes[ticker].diff_price_moving_averages():
            # average of the 50,200 moving averages minus the current stock price
            average_price_diff = -1 * quotes[ticker].diff_price_moving_averages()
            # buy more shares if the moving averages are less than the current stock price
            buying_shares_adjust = average_price_diff / latest_ticker_price
        else:
            buying_shares_adjust = 0

        # how much cash does thr trader want to use
        adjusted_cash = (buying_shares_adjust + 1) * cash
        # how many shares to buy
        buy_share_count = adjusted_cash / latest_ticker_price
        # 2 decimals max
        shares_count = round(max(buy_share_count * amplify, 0), 2)
        trades[ticker] = Order(shares=shares_count, cash=shares_count * latest_ticker_price, price=latest_ticker_price)

    return trades

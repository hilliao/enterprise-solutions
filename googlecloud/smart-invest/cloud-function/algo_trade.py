def recommend(amplify, orders, quotes):
    trades = {}

    for ticker in quotes:
        if isinstance(quotes[ticker], Exception):
            # assign the Exception to trade dictionary's value for later processing
            trades[ticker] = quotes[ticker]
            continue
        if 'fiftyDayAverage' not in quotes[ticker] or 'twoHundredDayAverage' not in quotes[ticker]:
            trades[ticker] = Exception("Failed to get fiftyDayAverage or twoHundredDayAverage from cached quotes")
            continue

        cash = float(orders[ticker])
        fiftyDayAverage = quotes[ticker]['fiftyDayAverage']
        twoHundredDayAverage = quotes[ticker]['twoHundredDayAverage']
        if 'Last' in quotes[ticker]:
            ticker_price = float(quotes[ticker]['Last'])
        else:
            ticker_price = quotes[ticker]['regularMarketPrice']

        # average of the moving averages minus the current stock price
        average_price_diff = ((fiftyDayAverage + twoHundredDayAverage) / 2 - ticker_price)
        # how much more or less does the trader want to buy
        buy_adjust = average_price_diff / ticker_price
        # how much cash does thr trader want to use
        adjusted_cash = (buy_adjust + 1) * cash
        # how many shares to buy
        buy_share_count = adjusted_cash / ticker_price
        # 2 decimals max
        shares_count = round(max(buy_share_count * amplify, 0), 2)
        trades[ticker] = {"shares": shares_count,
                          "cash": shares_count * ticker_price,
                          "price": ticker_price}
    return trades

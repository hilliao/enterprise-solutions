import requests


def recommend_buy(cash, amplify, fiftyDayAverage, twoHundredDayAverage, regularMarketPrice):
    # average of the moving averages minus the current stock price
    average_price_diff = ((fiftyDayAverage + twoHundredDayAverage) / 2 - regularMarketPrice)
    # how much more or less does the trader want to buy
    buy_adjust = average_price_diff / regularMarketPrice
    # how much cash does thr trader want to use
    adjusted_cash = (buy_adjust + 1) * cash
    # how many shares to buy
    buy_share_count = adjusted_cash / regularMarketPrice
    return max(buy_share_count * amplify, 0)


url = 'https://stock-quotes-slnskhfzsa-uw.a.run.app/?tickers=GOOGL,IVV'
response = requests.get(url=url)
regularMarketPrice = response.json()['GOOGL']['regularMarketPrice']
fiftyDayAverage = response.json()['GOOGL']['fiftyDayAverage']
twoHundredDayAverage = response.json()['GOOGL']['twoHundredDayAverage']

print('investing 10000 on GOOGL')
print(recommend_buy(10000, 1.5, fiftyDayAverage, twoHundredDayAverage, regularMarketPrice))
print(recommend_buy(10000, 1.2, fiftyDayAverage, twoHundredDayAverage, regularMarketPrice))
print(recommend_buy(10000, 1.1, fiftyDayAverage, twoHundredDayAverage, regularMarketPrice))
print(recommend_buy(10000, 1, fiftyDayAverage, twoHundredDayAverage, regularMarketPrice))  # no amplify
print(recommend_buy(10000, 0.8, fiftyDayAverage, twoHundredDayAverage, regularMarketPrice))
print(recommend_buy(10000, 0.5, fiftyDayAverage, twoHundredDayAverage, regularMarketPrice))
print(recommend_buy(10000, 0.25, fiftyDayAverage, twoHundredDayAverage, regularMarketPrice))
print(recommend_buy(10000, -5, fiftyDayAverage, twoHundredDayAverage, regularMarketPrice))
print(recommend_buy(10000, -10, fiftyDayAverage, twoHundredDayAverage, regularMarketPrice))
print(recommend_buy(10000, -20, fiftyDayAverage, twoHundredDayAverage, regularMarketPrice))

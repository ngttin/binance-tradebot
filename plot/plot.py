import sys
sys.path.append('..')

from queue import deque
import pylab
from binance.enums import *

from Trader import Trader
from config import TRADING_PAIR

analyze = Trader.analyze
client = Trader.client

class Plot(object):

    def get_hist_close(self):
        klines = client.get_historical_klines(TRADING_PAIR, KLINE_INTERVAL_1MINUTE, "1 day ago UTC")
        close_prices = [float(kline[4]) for kline in klines]
        return close_prices

    def analyze_all(self, data):
        close_prices = deque(data[:500], maxlen=500)
        remaining = data[len(close_prices):]
        analyzed_data = []
        analyzed_data.append(analyze(close_prices))
        for close in remaining:
            close_prices.append(close)
            analyzed_data.append(analyze(close_prices))
        return analyzed_data

    def plot(self, action='buy'):
        closes = self.get_hist_close()
        analyzed = self.analyze_all(closes)
        hull = [x['hull'] for x in analyzed]
        ema = [x['ema'] for x in analyzed]
        closes = [x['close'] for x in analyzed]
        buy_indices = [i for i, x in enumerate(analyzed) if x['buy_now']]
        buy_prices = [hull[x] for x in buy_indices]
        sell_indices = [i for i, x in enumerate(analyzed) if x['sell_now']]
        sell_prices = [hull[x] for x in sell_indices]
        x = range(len(hull))
        pylab.plot(x, hull, label='hull MA')
        pylab.plot(x, ema, label='exponential MA')
        pylab.plot(x, closes, label='close')
        if action == 'buy':
            pylab.scatter(buy_indices, buy_prices, c='g', label='buying point')
        elif action == 'sell':
            pylab.scatter(sell_indices, sell_prices, c='r', label='selling point')
        else: # both
            pylab.scatter(buy_indices, buy_prices, c='g', label='buying point')
            pylab.scatter(sell_indices, sell_prices, c='r', label='selling point')
        pylab.legend()
        pylab.show()

if __name__ == '__main__':
    plot = Plot()
    plot.plot(action='buy')

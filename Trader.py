# coding=utf-8

import time
import math
import sys
import threading
import logging
from queue import Queue, deque
import numpy as np

from pyti.hull_moving_average import hull_moving_average
from pyti.exponential_moving_average import exponential_moving_average

from binance.client import Client
from binance.enums import *

from config import *
from DictMap import DictMap
from Database import Database


class Trader(object):

    # Static variables
    logger = logging.getLogger("Trader")
    client = Client(API_KEY, API_SECRET)
    exchange_data_lock = threading.Lock()
    exchange_data = DictMap({})
    db_lock = threading.Lock()
    database = Database()
    close_prices = deque(maxlen=500)
    symbol_info = DictMap(client.get_symbol_info(symbol=TRADING_PAIR))
    order_queue = Queue()
    order_queue_lock = threading.Lock()
    analyzed_data = DictMap({})
    analyzed_data_lock = threading.Lock()
    buy_prices = []
    buy_prices_lock = threading.Lock()
    buying_lock = threading.Lock()
    selling_analyzed_data = DictMap({})
    buy_now_tracking = False

    def __init__(self):
        self.order_id = 0
        self.last_buy_price = None
        self.last_sell_price = None
        self.buying_lock_acquired = False
        self.partially_filled_wait_start_time = None
        self.order_wait_start_time = None
        self.stoploss_triggered = False

    def timeout(self, t, order_type='partially_filled'):
        """
        Check for timeout
        """
        if order_type == 'partially_filled':
            if int(time.time()) > (int(t) + PARTIALLY_FILLED_WAIT_TIME):
                return True
        else:
            if int(time.time()) > (int(t) + ORDER_WAIT_TIME):
                return True
        return False

    @staticmethod
    def get_exchange_data():
        """
        Get exchange data
        """
        def get_order_book(symbol):
            """
                {
                    "lastUpdateId": 1027024,
                    "bids": [
                        [
                            "4.00000000",     # PRICE
                            "431.00000000",   # QTY
                            []                # Can be ignored
                        ]
                    ],
                    "asks": [
                        [
                            "4.00000200",
                            "12.00000000",
                            []
                        ]
                    ]
                }
            """
            order_book = Trader.client.get_order_book(symbol=symbol, limit=10)
            return DictMap(order_book)
        def get_balance(asset):
            """
                {
                    "asset": "BTC",
                    "free": "4723846.89208129",
                    "locked": "0.00000000"
                }
            """
            balance = Trader.client.get_asset_balance(asset)
            return DictMap(balance)
        def get_order_book_ticker(symbol):
            """
                {
                    "symbol": "LTCBTC",
                    "bidPrice": "4.00000000",
                    "bidQty": "431.00000000",
                    "askPrice": "4.00000200",
                    "askQty": "9.00000000"
                }
            """
            ticker = Trader.client.get_orderbook_ticker(symbol=symbol)
            return DictMap(ticker)

        order_book = get_order_book(TRADING_PAIR)
        order_book_ticker = get_order_book_ticker(TRADING_PAIR)

        return DictMap({'order_book': order_book, 'ticker': order_book_ticker})

    @staticmethod
    def print_exchange_info():
        """
        Print exchange information
        """
        ask = Trader.exchange_data.ticker.askPrice
        bid = Trader.exchange_data.ticker.bidPrice
        diff = '%.8lf' % (float(ask) - float(bid))
        spread = '%.2lf' % ((float(ask)/float(bid) - 1) * 100)
        Trader.logger.info("*** ask: %s - bid: %s - diff: %s - spread: %s" % (ask, bid, diff, spread))

    @staticmethod
    def update_exchange_info():
        """
        Update the exchange data periodically.
        Start as a daemon thread in main program
        """
        while True:
            Trader.logger.debug("Updating exchange data...")
            start_time = time.time()
            Trader.exchange_data_lock.acquire()
            try:
                Trader.exchange_data = Trader.get_exchange_data()
            except Exception as e:
                Trader.logger.exception(e)

            Trader.exchange_data_lock.release()
            Trader.print_exchange_info()
            end_time = time.time()
            time_diff = end_time - start_time
            if time_diff < UPDATE_EXCHANGE_WAIT_TIME:
                Trader.logger.debug("Sleeping ...")
                time.sleep(UPDATE_EXCHANGE_WAIT_TIME - time_diff)


    @staticmethod
    def get_order_status(order_id):
        """
            {
                "symbol": "LTCBTC",
                "orderId": 1,
                "clientOrderId": "myOrder1",
                "price": "0.1",
                "origQty": "1.0",
                "executedQty": "0.0",
                "status": "NEW",
                "timeInForce": "GTC",
                "type": "LIMIT",
                "side": "BUY",
                "stopPrice": "0.0",
                "icebergQty": "0.0",
                "time": 1499827319559
            }
        """
        order = Trader.client.get_order(orderId=order_id, symbol=TRADING_PAIR)
        return DictMap(order)

    def buy(self, quantity, price):
        """
        Create buy order
        """
        price = self.format_price(price)
        quantity = self.format_quantity(quantity)
        self.logger.info("Buying %s at %s..." % (str(quantity), str(price)))
        try:     
            order = Trader.client.order_limit_buy(
                       symbol=TRADING_PAIR, quantity=quantity, 
                       price=price, newOrderRespType='RESULT')
        except Exception as e:
            self.logger.exception(e)
            raise
        self.last_buy_price = price
        self.logger.info("Buying order %s created." % order['orderId'])
        return order['orderId']

    def sell(self, quantity, price):
        """
        Create sell order
        """
        price = self.format_price(price)
        quantity = self.format_quantity(quantity)
        self.logger.info("Selling %s at %s..." % (str(quantity), str(price)))
        try:
            order = Trader.client.order_limit_sell(
                       symbol=TRADING_PAIR, quantity=quantity, 
                       price=price, newOrderRespType='RESULT')
        except Exception as e:
            self.logger.exception(e)
            raise
        self.last_sell_price = price
        self.logger.info("Selling order %s created." % order['orderId'])
        return order['orderId']

    def cancel(self, order_id):
        """
        Cancel open order
        """
        try:
            resp = Trader.client.cancel_order(symbol=TRADING_PAIR, orderId=order_id)
        except Exception as e:
            self.logger.exception(e)
            raise
        self.logger.info("Order %s has been cancelled." % resp['orderId'])
        return resp['orderId']

    @staticmethod
    def get_market_price():
        """
        Get market price
        """
        try:
            ticker = Trader.client.get_symbol_ticker(symbol=TRADING_PAIR)
        except Exception as e:
            Trader.logger.exception(e)
            raise
        return float(ticker['price'])

    @staticmethod
    def get_open_24h_price():
        """
        Get open price 24h
        """
        try:
            ticker = Trader.client.get_ticker(symbol=TRADING_PAIR)
        except Exception as e:
            Trader.logger.exception(e)
            raise
        return float(ticker['openPrice'])

    @staticmethod
    def get_last_close_price(limit=1):
        """
        Get recent close price
        """
        try:
            klines = Trader.client.get_klines(symbol=TRADING_PAIR, interval=KLINE_INTERVAL_1MINUTE, limit=limit)
        except Exception as e:
            Trader.logger.exception(e)
            raise
        close_prices = [float(kline[4]) for kline in klines]
        if len(close_prices) == 1:
            return close_prices[0]
        return close_prices

    @staticmethod
    def analyze(signal):
        """
        Analyze data
        """
        def calc_rsi(prices, n=14):
            deltas = np.diff(prices)
            seed = deltas[:n+1]
            up = seed[seed>=0].sum()/n
            down = -seed[seed<0].sum()/n
            rs = up/down
            rsi = np.zeros_like(prices)
            rsi[:n] = 100. - 100./(1.+rs)
            for i in range(n, len(prices)):
                delta = deltas[i-1] # cause the diff is 1 shorter
                if delta>0:
                    upval = delta
                    downval = 0.
                else:
                    upval = 0.
                    downval = -delta
                up = (up*(n-1) + upval)/n
                down = (down*(n-1) + downval)/n
                rs = up/down
                rsi[i] = 100. - 100./(1.+rs)
            return rsi
        def get_last_peak(data):
            np_data = np.array(data)
            peaks = (np_data >= np.roll(np_data, 1)) & (np_data > np.roll(np_data, -1))
            peaks = list(peaks[1:len(peaks)-1])
            idx = len(peaks) - peaks[::-1].index(True)
            return DictMap({'index': idx, 'value': data[idx]})
        def get_last_trough(data):
            np_data = np.array(data)
            troughs = (np_data <= np.roll(np_data, 1)) & (np_data < np.roll(np_data, -1))
            troughs = list(troughs[1:len(troughs)-1])
            idx = len(troughs) - troughs[::-1].index(True)
            return DictMap({'index': idx, 'value': data[idx]})

        data = list(signal)
        ema = exponential_moving_average(data[-EMA_PERIOD:], EMA_PERIOD)[-1]
        if Trader.selling_analyzed_data:
            hull_data = hull_moving_average(data[-(HULL_PERIOD+30):], HULL_PERIOD)
        else:
            hull_data = hull_moving_average(data, HULL_PERIOD)

        # @TODO: clean up the code
        sell_now  = False
        if not Trader.selling_analyzed_data: # first time
            hd = [x for x in hull_data if x >= 0]
            last_peak = get_last_peak(hd)
            last_trough = get_last_trough(hd)
            if last_peak.index > last_trough.index:
                Trader.selling_analyzed_data.last_is_trough = False
            else:
                Trader.selling_analyzed_data.last_is_trough = True
            Trader.selling_analyzed_data.peak = last_peak.value
            Trader.selling_analyzed_data.trough = last_trough.value
            Trader.selling_analyzed_data.previous_peak = None
            Trader.selling_analyzed_data.previous_trough = None
            Trader.selling_analyzed_data.last = hull_data[-1]
        else:
            last = hull_data[-1]
            height = Trader.selling_analyzed_data.peak - Trader.selling_analyzed_data.trough
            if Trader.selling_analyzed_data.last_is_trough:
                retrace_height = last - Trader.selling_analyzed_data.trough
            else:
                retrace_height = Trader.selling_analyzed_data.peak - last

            retrace_perc = retrace_height/height * 100.0
            if Trader.selling_analyzed_data.last_is_trough:
                if retrace_perc < 0:
                    Trader.selling_analyzed_data.last_is_trough = False
                    if Trader.selling_analyzed_data.previous_trough:
                        Trader.selling_analyzed_data.trough = Trader.selling_analyzed_data.previous_trough
                if last < Trader.selling_analyzed_data.last:
                    if retrace_perc > IGNORE_SMALL_PEAK_PERCENTAGE:
                        Trader.selling_analyzed_data.last_is_trough = False
                        Trader.selling_analyzed_data.previous_peak = Trader.selling_analyzed_data.peak
                        Trader.selling_analyzed_data.peak = Trader.selling_analyzed_data.last
            else:
                if retrace_perc < 0:
                    Trader.selling_analyzed_data.last_is_trough = True
                    if Trader.selling_analyzed_data.previous_peak:
                        Trader.selling_analyzed_data.peak = Trader.selling_analyzed_data.previous_peak
                if last > Trader.selling_analyzed_data.last: # got a new reversal
                    if retrace_perc > IGNORE_SMALL_PEAK_PERCENTAGE:
                        Trader.selling_analyzed_data.last_is_trough = True
                        Trader.selling_analyzed_data.previous_trough = Trader.selling_analyzed_data.trough
                        Trader.selling_analyzed_data.trough = Trader.selling_analyzed_data.last
                if retrace_perc >= SELL_MAX_RETRACEMENT_PERCENTAGE:
                    sell_now = True
            Trader.selling_analyzed_data.last = last
        Trader.logger.debug("selling analyze data: %s" % str(Trader.selling_analyzed_data))

        rsi = calc_rsi(data[-(RSI_PERIOD+1):], RSI_PERIOD)[-1]
        ma_spread = 100*(ema/hull_data[-1] - 1)
        Trader.logger.debug("ema - rsi - ma_spread: %s - %s - %s" % (str(ema), str(rsi), str(ma_spread)))
        buy_now = False

        if rsi < RSI_OVERSOLD_PERCENTAGE and ma_spread > MIN_MA_SPREAD and hull_data[-1] <= hull_data[-2]:
                Trader.buy_now_tracking = True
        else:
            if Trader.buy_now_tracking and hull_data[-1] > hull_data[-2] and Trader.selling_analyzed_data.last_is_trough:
                height = Trader.selling_analyzed_data.peak - Trader.selling_analyzed_data.trough
                retrace_height = last - Trader.selling_analyzed_data.trough
                retrace_perc = retrace_height/height * 100.0
                if retrace_perc >= BUY_MAX_RETRACEMENT_PERCENTAGE:
                    buy_now = True
                    Trader.buy_now_tracking = False

        return DictMap({'buy_now': buy_now, 'sell_now': sell_now, 'ema': ema, 'hull': hull_data[-1], 'close': data[-1]})

    @staticmethod
    def analyze_market_data():
        """
        Analyze market data
        Start as daemon thread
        """
        server_time = Trader.client.get_server_time()
        server_time_offset = int(time.time()*1000) - int(server_time['serverTime'])
        Trader.logger.debug("Time offset: %d" % server_time_offset)
        close_time = 0
        while True:
            Trader.logger.debug("RUNNING...")
            st = time.time()
            if len(Trader.close_prices) == 0: # first time fetch
                data = Trader.client.get_klines(symbol=TRADING_PAIR, interval=KLINE_INTERVAL_1MINUTE, limit=500)
                for point in data:
                    Trader.close_prices.append(float(point[4]))
                close_time = int(data[-1][6])
            else:
                current_time_with_offset = int(time.time() * 1000) - server_time_offset
                Trader.logger.debug("close time: " + str(close_time))
                Trader.logger.debug("current time with offset: " + str(current_time_with_offset))
                if  current_time_with_offset > close_time:
                    try:
                        data = Trader.client.get_klines(symbol=TRADING_PAIR, interval=KLINE_INTERVAL_1MINUTE, limit=2)
                    except Exception as e:
                        Trader.logger.exception(e)
                        continue
                    close_time_new = int(data[-1][6])
                    if close_time != close_time_new: # to avoid duplicate
                        close_time = close_time_new
                        Trader.close_prices.append(float(data[0][4]))
                        Trader.analyzed_data_lock.acquire()
                        Trader.analyzed_data = Trader.analyze(Trader.close_prices)
                        Trader.logger.debug(str(Trader.analyzed_data))
                        Trader.analyzed_data_lock.release()
            et = time.time()
            if (et - st) < ANALYZE_WAIT:
                Trader.logger.debug("SLEEPING...")
                time.sleep(ANALYZE_WAIT - (et-st))

    @staticmethod
    def check_order():
        """
        Check status for orders in queue
        Start as daemon thread
        """
        while True:
            Trader.order_queue_lock.acquire()
            order_queue_empty = Trader.order_queue.empty()
            Trader.order_queue_lock.release()
            if not order_queue_empty:
                Trader.order_queue_lock.acquire()
                order_id = Trader.order_queue.get()
                Trader.order_queue_lock.release()
                Trader.logger.info("Checking for order #%d status..." % order_id)
                order_status = Trader.get_order_status(order_id)
                Trader.logger.info("Order #%s status: %s" % (order_id, order_status.status))
                Trader.db_lock.acquire()
                order_data = {'order_id': str(order_id), 'price': order_status.price, 'orig_quantity': order_status.origQty, 
                                'executed_quantity': order_status.executedQty, 'side': order_status.side, 
                                'time': order_status.time, 'status': order_status.status}
                Trader.database.order_update(order_data)
                Trader.db_lock.release()
                Trader.logger.info("Checking done for order #%d" % order_id)
            else:
                Trader.logger.info("Order queue is empty. Waiting for new order...")
                time.sleep(CHECK_ORDER_WAIT_TIME)

    def update_balance(self, name, initial_amount=None, initial_quantity=None, executed_quantity=None, price=None, side=None, first_time=False):
        """
        Update balance to database
        """
        Trader.logger.debug("Updating balance...")
        data = {'thread_name': name, 'pairs': {}}
        modifier =  1 - FEE/100.0
        Trader.db_lock.acquire()
        if first_time:
            if not initial_amount:
                data['pairs']['initial_amount'] = '0.0'
                data['pairs']['current_amount'] = '0.0'
            else:
                data['pairs']['initial_amount'] = str(initial_amount)
                data['pairs']['current_amount'] = str(initial_amount)
            if not initial_quantity:
                data['pairs']['initial_quantity'] = '0.0'
                data['pairs']['current_quantity'] = '0.0'
            else:
                data['pairs']['initial_quantity'] = str(initial_quantity)
                data['pairs']['current_quantity'] = str(initial_quantity)
        else:
            executed_quantity = float(executed_quantity)
            price = float(price)
            current_amount = float(Trader.database.trader_read(name, key='current_amount')['pairs']['current_amount'])
            current_quantity = float(Trader.database.trader_read(name, key='current_quantity')['pairs']['current_quantity'])
            if executed_quantity > 0.0:
                if side == 'SELL':
                    current_quantity = current_quantity - executed_quantity
                    current_amount = current_amount + executed_quantity*price*modifier
                else: #BUY
                    current_quantity = current_quantity + executed_quantity*modifier
                    current_amount = current_amount - executed_quantity*price
            else:
                return
            data['pairs']['current_amount'] = str(current_amount)
            data['pairs']['current_quantity'] = str(current_quantity)

        Trader.database.trader_update(data)
        Trader.db_lock.release()

    def validate(self, quantity, price):
        """
        Check validity of an order before sending it to the exchange
        """
        filters = Trader.symbol_info.filters
        price_filter = filters[0]
        lot_size_filter = filters[1]
        notional_filter = filters[2]
        min_price = float(price_filter['minPrice'])
        max_price = float(price_filter['maxPrice'])
        tick_size = float(price_filter['tickSize'])
        min_quantity = float(lot_size_filter['minQty'])
        max_quantity = float(lot_size_filter['maxQty'])
        step_size = float(lot_size_filter['stepSize'])
        min_notional = float(notional_filter['minNotional'])
        if price < min_price or price > max_price:
            raise Exception('PRICE_EXCEPTION')
        if quantity < min_quantity or quantity > max_quantity:
            raise Exception('QUANTITY_EXCEPTION')
        if price*quantity < min_notional:
            raise Exception('MIN_NOTIONAL')
        return True

    def amount_to_quantity(self, amount, price):
        """
        Calculate quantity
        """
        quantity = amount / price
        return self.format_quantity(quantity)

    def format_quantity(self, quantity):
        """
        Format quantity
        """
        step_size = float(Trader.symbol_info.filters[1]['stepSize'])
        return round(float(step_size * math.floor(float(quantity)/step_size)), 8)


    def format_price(self, price):
        """
        Format price
        """
        tick_size = float(Trader.symbol_info.filters[0]['tickSize'])
        return round(float(tick_size * math.floor(float(price)/tick_size)), 8)

    def calc_profit(self, price):
        """
        Calculate the profit
        """
        profit = (price/self.last_buy_price - 1) * 100
        return profit

    def is_profitable(self, price):
        """
        Check for profitability
        """
        if self.calc_profit(price) >= PREFERRED_PROFIT:
            return True
        return False

    def is_stoploss(self, price):
        """
        Check for loss
        """
        loss_perc = 100*(1-price/float(self.last_buy_price))
        if loss_perc >= STOPLOSS_TRIGGER_PERCENTAGE:
            return True
        return False

    def calc_profitable_price(self):
        """
        Calculate the profitable price
        """
        price = self.last_buy_price * (1 + PREFERRED_PROFIT/100.0)

        return self.format_price(price)

    def calc_buy_price(self):
        """
        Calculate buy price
        """
        order_book = self.exchange_data.order_book
        orders = order_book.bids
        last_ask = float(order_book.asks[0][0])
        quantities = [float(order[1]) for order in orders]
        prices = [float(order[0]) for order in orders]
        for i in range(1, len(quantities)):
            if sum(quantities[:i]) >= (QUANTITY_COEFFICIENT * INITIAL_AMOUNT/prices[0]):
                break
        optimal_prices = prices[:i]
        tick_size = float(Trader.symbol_info.filters[0]['tickSize'])  
        buy_price = optimal_prices[-1] 
        while True:
            buy_price = buy_price + tick_size
            if buy_price not in optimal_prices:
                break
        buy_price = buy_price + BUY_PRICE_TICK_OFFSET * tick_size
        if buy_price > last_ask:
            buy_price = last_ask
        return self.format_price(buy_price)


    def calc_sell_price(self):
        """
        Calculate sell price
        """
        order_book = self.exchange_data.order_book
        orders = order_book.asks
        last_bid = float(order_book.bids[0][0])
        quantities = [float(order[1]) for order in orders]
        prices = [float(order[0]) for order in orders]
        for i in range(1, len(quantities)):
            if sum(quantities[:i]) >= (QUANTITY_COEFFICIENT * INITIAL_AMOUNT/prices[0]):
                break
        optimal_prices = prices[:i]
        tick_size = float(Trader.symbol_info.filters[0]['tickSize'])
        sell_price = optimal_prices[-1] 
        while True:
            sell_price = sell_price - tick_size
            if sell_price not in optimal_prices:
                break
        sell_price = sell_price - SELL_PRICE_TICK_OFFSET * tick_size
        if sell_price < last_bid:
            sell_price = last_bid
        return self.format_price(sell_price)


    def calc_sell_quantity(self):
        """
        Calculate sell quantity
        """
        name = threading.currentThread().getName()
        Trader.db_lock.acquire()
        balance = float(Trader.database.trader_read(name, key='current_quantity')['pairs']['current_quantity'])
        Trader.db_lock.release()
        return self.format_quantity(balance)

    def calc_buy_quantity(self, price):
        """
        Calculate buy quantity
        """
        name = threading.currentThread().getName()
        Trader.db_lock.acquire()
        balance = float(Trader.database.trader_read(name, key='current_amount')['pairs']['current_amount'])
        Trader.db_lock.release()
        return self.amount_to_quantity(balance, price)

    def calc_price_range(self, price=None, side='buy'):
        """
        Calculate price range. 
        If the price of an open order is out of this range, cancel that order and place it again with new price.
        """
        order_book = self.exchange_data.order_book
        tick_size = float(Trader.symbol_info.filters[0]['tickSize'])
        if side == 'buy':
            orders = order_book.bids
        else: #sell
            orders = order_book.asks
        lower_price = float(orders[0][0])
        if price:
            my_price = float(price)
            if my_price == float(orders[0][0]) and \
                           abs(my_price - float(orders[1][0])) > DIFF_TICKS * tick_size:
                lower_price = float(orders[1][0])
        quantities = [float(order[1]) for order in orders]
        for i in range(1, len(quantities)):
            if sum(quantities[:i]) >= (QUANTITY_COEFFICIENT * INITIAL_AMOUNT/lower_price):
                break
        upper_price = float(orders[i-1][0])

        return [lower_price, upper_price]

    def buy_action(self, status=None):
        self.logger.info("*** BUY ACTION ***")
        if status == 'filled' or status == 'cancelled_partially_filled':
            if status == 'filled' and self.stoploss_triggered:
                self.stoploss_triggered = False
            self.partially_filled_wait_start_time = None
            self.order_wait_start_time = None
            Trader.buy_prices_lock.acquire()
            Trader.logger.debug("Removing price %s from buy_prices" % (str(self.last_buy_price)))
            Trader.logger.debug("buy_prices: %s" % str(Trader.buy_prices))
            Trader.buy_prices = list(set(Trader.buy_prices))
            try:
                Trader.buy_prices.remove(self.last_buy_price)
            except Exception as e:
                Trader.logger.info("Probably the buy order was partially filled but not enough to sell.")
                Trader.logger.exception(e)
            Trader.logger.debug("buy_prices: %s" % str(Trader.buy_prices))
            Trader.buy_prices_lock.release()
        if not self.buying_lock_acquired:
            # Acquire the lock until the buying action is complete
            # It blocks other threads to avoid multiple buy orders at a time
            Trader.logger.debug("Acquiring buying lock...")
            Trader.buying_lock.acquire()
            self.buying_lock_acquired = True
            Trader.logger.debug("Buying lock acquired.")
        if not status or status == 'filled' or status == 'cancelled_partially_filled':
            self.order_id = 0
            buy_price = self.calc_buy_price()
            Trader.buy_prices_lock.acquire()
            buy_prices = Trader.buy_prices
            Trader.buy_prices_lock.release()
                
            Trader.analyzed_data_lock.acquire()
            buy_now = Trader.analyzed_data.buy_now
            ema = Trader.analyzed_data.ema
            Trader.analyzed_data_lock.release()

            if not ema:
                return
            perc = 100 * (ema/buy_price - 1)
            Trader.logger.info("ema - buy_price percentage: %.2lf -  buy: %s" % (perc, str(buy_price)))
            if perc < EMA_TO_BUY_PRICE_PERCENTAGE:
                return
            if not buy_now:
                return
            if len(buy_prices) > 0:
                Trader.logger.debug("buy_prices: %s" % str(buy_prices))
                min_price = min(buy_prices)
                min_price_perc = (min_price/buy_price-1)*100
                if min_price_perc >= BUY_MORE_PRICE_PERCENTAGE:
                    pass
                else:
                    Trader.logger.info("There are incomplete actions. Waiting...")
                    return

            quantity = self.calc_buy_quantity(buy_price)
            try:
                self.validate(quantity, buy_price)
                self.order_id = self.buy(quantity, buy_price)
            except Exception as e:
                Trader.logger.exception(e)
                Trader.logger.info("An error occurred during buying.")
                Trader.logger.debug("Releasing the buying lock...")
                self.buying_lock_acquired  = False
                Trader.buying_lock.release()

        elif status == 'new' or status == 'partially_filled':
            if status == 'new':
                if not self.order_wait_start_time:
                    self.order_wait_start_time = time.time()
                if not self.timeout(self.order_wait_start_time, order_type='new'):
                    return

            if status == 'partially_filled':
                if not self.partially_filled_wait_start_time:
                    self.partially_filled_wait_start_time = time.time()
                if not self.timeout(self.partially_filled_wait_start_time):
                    Trader.logger.info("Partially filled. Waiting for order to be filled...")
                    return
                else:
                    Trader.logger.info("Waiting for order timed out.")

            price_range = self.calc_price_range(side='buy', price=self.last_buy_price)
            self.logger.debug("BUY_ACTION: price_range: %s" % str(price_range))
            # if the price is not in range, cancel and try to place an order again
            if self.last_buy_price < price_range[0] or self.last_buy_price > price_range[1]:
                try:
                    self.cancel(self.order_id)
                except Exception as e:
                    Trader.logger.exception(e)


    def sell_action(self, status=None):
        self.logger.info("*** SELL ACTION ***")
        sell_price = self.calc_sell_price()
        quantity = self.calc_sell_quantity()
        profitable_price = self.calc_profitable_price()

        if not status or status == 'filled' or status == 'cancelled' or status == 'cancelled_partially_filled':
            if status =='filled' or status == 'cancelled_partially_filled':
                self.partially_filled_wait_start_time = None
                self.order_wait_start_time = None
                Trader.buy_prices_lock.acquire()
                Trader.logger.debug("Appending price %s to buy_prices" % (str(self.last_buy_price)))
                Trader.logger.debug("buy_prices: %s" % str(Trader.buy_prices))
                Trader.buy_prices.append(self.last_buy_price)
                Trader.logger.debug("buy_prices: %s" % str(Trader.buy_prices))
                Trader.buy_prices_lock.release()
                Trader.logger.debug("Releasing buying lock...")
                try:
                    Trader.buying_lock.release()
                except Exception as e:
                    Trader.logger.exception(e)
                else:
                    self.buying_lock_acquired = False
            self.order_id = -1
            Trader.analyzed_data_lock.acquire()
            sell_now = Trader.analyzed_data.sell_now
            Trader.analyzed_data_lock.release()

            if self.is_stoploss(sell_price):
                Trader.logger.info("Stop loss.")
                self.stoploss_triggered = True

            if not sell_now and not stoploss_triggered:
                Trader.logger.info("waiting for sell signal.")
                return

            if self.stoploss_triggered:
                loss_perc = 100*(1-sell_price/float(self.last_buy_price))
                if loss_perc <= STOPLOSS_PERCENTAGE and not sell_now:
                    Trader.logger.info("Stop loss: waiting for sell signal.")
                    return
                if loss_perc <= STOPLOSS_PERCENTAGE or loss_perc >= IMMEDIATELY_STOPLOSS_PERCENTAGE:
                    Trader.logger.info("Selling at %.2lf percent loss." % loss_perc)
                    quantity = self.calc_sell_quantity()
                else:
                    return
            elif self.is_profitable(sell_price):
                Trader.logger.info("The profit is %.2lf. Try to sell it. Least profitable_price is %.8lf." % (self.calc_profit(sell_price), profitable_price))
            else:
                Trader.logger.info("Least profitable_price is %.8lf." % (profitable_price))
                return
            try:
                self.validate(quantity, sell_price)
                self.order_id = self.sell(quantity, sell_price)
            except Exception as e:
                Trader.logger.exception(e)
                if status == 'cancelled_partially_filled':
                    raise
                Trader.logger.error("Cannot sell. Please handle it manually. Exiting...")
                sys.exit(1)

        elif status == 'new' or status == 'partially_filled':
            if status == 'new':
                if not self.order_wait_start_time:
                    self.order_wait_start_time = time.time()
                if not self.timeout(self.order_wait_start_time, order_type='new'):
                    return

            if status == 'partially_filled':
                if not self.partially_filled_wait_start_time:
                    self.partially_filled_wait_start_time = time.time()
                if not self.timeout(self.partially_filled_wait_start_time):
                    Trader.logger.info("Waiting for order to be filled...")
                    return
                else:
                    Trader.logger.info("Waiting for filled order timed out.")

            price_range = self.calc_price_range(price=self.last_sell_price)
            self.logger.debug("SELL_ACTION: last_sell: %s - sell_price: %s - price_range: %s" % (str(self.last_sell_price),str(sell_price), str(price_range)))
            if self.is_profitable(sell_price) or self.stoploss_triggered:
                if self.last_sell_price > price_range[0] or self.last_sell_price < price_range[1]:
                    try:
                        self.cancel(self.order_id)
                    except Exception as e:
                        Trader.logger.exception(e)
                        Trader.logger.info("Cannot cancel order #%s. Maybe it has already fully filled." % str(self.order_id))


    def trade(self):
        """
        Trading logic
        """
        name = threading.currentThread().getName()
        self.logger.info("%s starting...", name)
        self.update_balance(name, initial_amount=INITIAL_AMOUNT, first_time=True)
        while True:
            # make a copy of exchange data
            Trader.exchange_data_lock.acquire()
            self.exchange_data = Trader.exchange_data
            Trader.exchange_data_lock.release()
            if self.order_id == 0:
                self.buy_action()
            elif self.order_id == -1:
                self.sell_action()
            else:
                Trader.db_lock.acquire()
                order_data = Trader.database.order_read(self.order_id)
                Trader.db_lock.release()
                if not order_data:
                    Trader.logger.info("Waiting for order data to be available... Sleeping for a while...")
                    time.sleep(CHECK_ORDER_WAIT_TIME)
                else:
                    order_data = DictMap(order_data)
                    if order_data.status == 'NEW' and order_data.side == 'BUY':
                        self.buy_action(status='new')
                    elif order_data.status == 'NEW' and order_data.side == 'SELL':
                        self.sell_action(status='new')
                    elif order_data.status == 'FILLED' and order_data.side == 'BUY':
                        self.update_balance(name, executed_quantity=order_data.executed_quantity, price=order_data.price, side='BUY')
                        self.sell_action(status='filled')
                    elif order_data.status == 'FILLED' and order_data.side == 'SELL':
                        self.update_balance(name, executed_quantity=order_data.executed_quantity, price=order_data.price, side='SELL')
                        self.buy_action(status='filled')
                    elif order_data.status == 'PARTIALLY_FILLED' and order_data.side == 'BUY':
                        self.buy_action(status='partially_filled')
                    elif order_data.status == 'PARTIALLY_FILLED' and order_data.side == 'SELL':
                        self.sell_action(status='partially_filled')
                    elif order_data.status == 'CANCELED':
                        #if the order was cancelled and executed_quantity is 0, handle it as a normal case
                        if float(order_data.executed_quantity) == 0.0:
                            if order_data.side == 'BUY':
                                self.buy_action()
                            else:
                                self.sell_action()
                        # buy all with the current amount
                        # if the amount is not enough, sell more
                        else:
                            self.update_balance(name, executed_quantity=order_data.executed_quantity, price=order_data.price, side=order_data.side)
                            Trader.db_lock.acquire()
                            current_amount = float(Trader.database.trader_read(name, key='current_amount')['pairs']['current_amount'])
                            current_quantity = float(Trader.database.trader_read(name, key='current_quantity')['pairs']['current_quantity'])
                            Trader.db_lock.release()
                            if current_quantity*float(order_data.price) > float(Trader.symbol_info.filters[2]['minNotional']):
                                if order_data.side == 'BUY':
                                    self.sell_action(status='cancelled_partially_filled')
                                else: # sell more when the selling order was partially filled
                                    self.sell_action()
                            else:
                                try:
                                    self.buy_action(status='cancelled_partially_filled')
                                except:
                                    Trader.logger.info('Order was partially filled. Unable to buy or sell. Please handle it manually.')
                                    Trader.logger.info('%s exits now...' % name)
                                    sys.exit(1)
            # Only put an order to the queue if its orderId > 0
            if int(self.order_id) > 0:
                Trader.order_queue_lock.acquire()
                Trader.order_queue.put(self.order_id)
                Trader.order_queue_lock.release()

            time.sleep(TRADER_WAIT_TIME)

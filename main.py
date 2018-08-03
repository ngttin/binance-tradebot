import time
import threading
import logging

from Trader import Trader

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(threadName)s - %(message)s')

    trader_1 = Trader()
    trader_2 = Trader()
    trader_3 = Trader()
    trader_4 = Trader()
    
    thread_update_exchange = threading.Thread(target=Trader.update_exchange_info, name="Exchange Updater")
    thread_update_exchange.daemon = True

    thread_analyze_market = threading.Thread(target=Trader.analyze_market_data, name="Market Analyzer")
    thread_analyze_market.daemon = True

    thread_check_order = threading.Thread(target=Trader.check_order, name="Order Checker")
    thread_check_order.daemon = True

    thread_trader_1 = threading.Thread(target=trader_1.trade, name="trader_1")
    thread_trader_2 = threading.Thread(target=trader_2.trade, name="trader_2")
    thread_trader_3 = threading.Thread(target=trader_3.trade, name="trader_3")
    thread_trader_4 = threading.Thread(target=trader_4.trade, name="trader_4")

    thread_update_exchange.start()
    thread_analyze_market.start()
    thread_check_order.start()

    thread_trader_1.start()
    thread_trader_2.start()
    thread_trader_3.start()
    thread_trader_4.start()

    while True:
        logging.debug('Sleep 60 sec...')
        time.sleep(60)



if __name__ == '__main__':
    main()

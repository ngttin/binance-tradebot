# coding=utf-8

API_KEY = 'YOUR_API_KEY'
API_SECRET = 'YOUR_API_SECRET'
TRADING_PAIR = 'NASETH'
ANALYZE_WAIT = 5 # (seconds), analyze data for every ANALYZE_WAIT seconds
UPDATE_EXCHANGE_WAIT_TIME = 1.5 # (seconds) update the exchange info for every UPDATE_EXCHANGE_WAIT_TIME
CHECK_ORDER_WAIT_TIME = 1 # (seconds), check orders in queue for every CHECK_ORDER_WAIT_TIME seconds
TRADER_WAIT_TIME = 2 # (seconds), dont need to change this
PARTIALLY_FILLED_WAIT_TIME = 180 # (seconds), if the order is not fully filled (because we use limit order, not the market order), keep it for PARTIALLY_FILLED_WAIT_TIME seconds
ORDER_WAIT_TIME = 5 # (seconds), place an order and keep it for ORDER_WAIT_TIME seconds before cancelling it and place again
FEE = 0.1 # (percent), =MAX(maker, taker)

# ORDER BOOK (buy or sell)
#  <-> ----- <-- your order will be placed here
#   |
#   | <--- OFFSET
#   |
#  <-> ----- <-- 1st order
#      ----- <-- 2nd order
SELL_PRICE_TICK_OFFSET = 1 # (ticks) 
BUY_PRICE_TICK_OFFSET = 1 # (ticks) 
BUY_MORE_PRICE_PERCENTAGE = 1.0 # (percent), buy more base asset if the price drops below BUY_MORE_PRICE_PERCENTAGE percent
RSI_PERIOD = 14 # Relative Strength Index period
RSI_OVERSOLD_PERCENTAGE = 30.0 # (percent)
RSI_OVERBOUGHT_PERCENTAGE = 70.0 # (percent), set this to 0.0 if you want to take profit when preferred profit is met

# <->------- ask
#  |
#  | <----- spread
#  |
# <->------- bid
BID_ASK_SPREAD = 0.01 # (percent), minimum spread between bid and ask, this is useful if you want to execute trade based on that spread
PREFERRED_PROFIT = 1.0 # (percent), minimum profit you want for each trade (buy-sell)
QUANTITY_COEFFICIENT = 0.2 # use this number to calc the range of price
INITIAL_AMOUNT = 1.0 # Initial amount per trading thread

# ORDER BOOK (buy or sell)
#  <-> ----- <-- your price
#   |
#   | <--- DIFF_TICKS
#   |
#  <-> ----- <-- 2nd order
#      ----- <-- 3rd order
DIFF_TICKS = 3 # (ticks), if the diff between your order and 2nd order is greater than DIFF_TICKS, the price will be re-calculated


#                    \
#                     \       /<- stop loss
#                      \     /
#         triggered->   \___/
#                        \
#                         \
# immediately stop loss -> \__

STOPLOSS_TRIGGER_PERCENTAGE = 3.0 # (percent), trigger but not stop loss yet
STOPLOSS_PERCENTAGE = 1.0 # (percent), hint: use negative number if you want to lower the preferred profit
IMMEDIATELY_STOPLOSS_PERCENTAGE = 5.0 # (percent), immediately stop loss if the loss is over this number

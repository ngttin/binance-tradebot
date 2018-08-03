# Binance Trading Bot

This is an experimental bot for auto trading on Binance Exchange written in Python. You use it at your own risk. I am not responsible for any trades the bot has made.

## Dependencies

+ [future](https://github.com/PythonCharmers/python-future)
+ [python-binance](https://github.com/sammchardy/python-binance)
+ [pyti](https://github.com/kylejusticemagnuson/pyti)
+ [numpy](https://github.com/numpy/numpy)


## Prerequisites

1. First, register an account on [Binance](https://www.binance.com/register.html?ref=22639199), then deposit some coins. If you have already had, skip this step.
2. [Create New API key](https://www.binance.com/userCenter/createApi.html) with proper permissions.

## Install & Run The Bot

1. Install all dependencies listed above
2. Clone this repository to your local
3. Edit `config.py`
4. Edit `main.py`
5. Copy `sample.tradebot.db` to `tradebot.db` in `database/`
6. Run the bot with `python main.py`, if you want to log the output, you can run it with `python -u main.py 2>&1 | tee logfile`

## Features

+ Support multiple orders
+ Stop loss implementation
+ Configurable parameters


# Plotting tool

**To use this tool, you have to install `matplotlib`.**

When you change parameters in configuration file, use this tool to observe how these parameters affect the buy and sell signals on historical data.

# Todo

+ Update README.md
+ Add more trading strategies (indicators)
+ Update UI
+ Resume previous trading session

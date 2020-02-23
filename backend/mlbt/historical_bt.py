# AUTOGENERATED! DO NOT EDIT! File to edit: dev/14_historical_bt.ipynb (unless otherwise specified).

__all__ = ['simulate_pnl', 'estimate_trading_costs', 'SLIPPAGE_ESTIMATE', 'COMMISSION_ESTIMATE']

# Cell

import pandas as pd
import numpy as np
import logging

SLIPPAGE_ESTIMATE = 0.25  # We estimate we'll pay 1/4 of the bid-ask spread
COMMISSION_ESTIMATE = 1

def simulate_pnl(config, close, signal, pos_size=50000, pos_cap_multi=1000, init_capital=7e7):
    pos_cap = pos_size * pos_cap_multi
    signal = signal.div(signal.sum(axis=1), axis=0)

    # dirty hack to get a rough value for various volatilities
    volatility = pd.DataFrame(1, index=close.index, columns=close.columns)
    for col in close.columns:
        volatility[col] = np.log(pd.Series(close[col].unique())).diff().std()

    currency_pos = (pos_size * signal / volatility).clip(-pos_cap, pos_cap)
    profits_gross = (close.pct_change() * currency_pos.shift(periods=1)).sum(axis=1)

    profits_net, stats = estimate_trading_costs(
        config, close, currency_pos, profits_gross
    )
    nav_net = (1 + (profits_net) / init_capital).cumprod()

    return nav_net, None, stats


def estimate_trading_costs(config, prices, currency_pos, profits):
    # TODO: This code is old and needs refactoring
    # Do copies to shapes of prices dataframe and allow for easy multiplication later
    multipliers = prices.copy()
    for col in multipliers.columns:
        multipliers[col] = config["symbols_map"].loc[col, "multiplier"]

    tick_sizes = prices.copy()
    for col in tick_sizes.columns:
        tick_sizes[col] = config["symbols_map"].loc[col, "mintick"]

    commissions = pd.DataFrame(COMMISSION_ESTIMATE, index=prices.index, columns=prices.columns)

    num_contracts = currency_pos.div(multipliers.mul(prices)).round(0)

    contracts_traded = num_contracts.diff().abs()
    slippage = contracts_traded.mul(tick_sizes.mul(multipliers)) * SLIPPAGE_ESTIMATE
    commissions_cost = contracts_traded.mul(commissions)
    trading_costs = commissions_cost + slippage
    daily_trading_costs = trading_costs.fillna(0).sum(axis=1)
    profits_less_costs = profits - daily_trading_costs

    trade_count = contracts_traded.astype(bool).astype(float).sum().sum()

    stats = {
        "trade_count": trade_count.sum().sum(),
        "contracts_traded": contracts_traded.sum().sum(),
        "total_trading_costs": daily_trading_costs.sum(),
        "commissions_cost": commissions_cost.sum(axis=1).sum(),
        "slippage": slippage.sum(axis=1).sum(),
    }

    return profits_less_costs, stats
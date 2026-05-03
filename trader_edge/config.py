"""Constants used across the engine."""

TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.07  # India 10y bond ballpark; override per trade if needed
DEFAULT_BROKERAGE_PER_SHARE = 0.20  # paise per share on each leg, conservative
DEFAULT_SLIPPAGE_BPS = 3  # basis points each side

# Variance risk premium adjustment: implied vol is typically X vol-points above
# realized for indices, less for single names. Used to convert risk-neutral
# probabilities to "real-world" probabilities when requested.
INDEX_VRP_VOL_POINTS = 4.0
SINGLE_NAME_VRP_VOL_POINTS = 1.5

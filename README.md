# trader-edge

A deterministic pre-trade risk engine for Indian equities and F&O. Uses the
options chain as a free oracle for cash-segment trades. **No LLMs in the
reasoning loop** — every number is a closed-form expression or a numerical
operation on observable market prices.

## Why this exists

SEBI's 2024 study found that ~89% of individual F&O traders lose money. The
reason is rarely bad indicators; it's that retail tools surface **prices**,
not **probabilities**. A trader sees "1:3 R:R" on screen and thinks they have
edge — when in fact the headline ratio ignores how often the stop will get
hit by noise, what the options market is implicitly pricing as the chance of
the target, and the joint dynamics of which level hits first.

`trader-edge` computes the four numbers that change the conversation:

1. **P(stop hit by realized-vol noise alone)** — reflection principle on
   geometric Brownian motion. If your stop is at noise distance, you will be
   stopped out by random walk before your thesis has a chance.
2. **P(touch target/stop) implied by the option chain** — fit IV smile from
   the chain, run the same first-passage formula at each barrier's IV. This
   is the market's own forecast.
3. **Joint first-passage probabilities** — Monte Carlo at implied vol to
   resolve "who hits first" given both barriers are alive.
4. **True expected value** — net of brokerage and slippage, in rupees.

The output is a verdict and concrete alternatives: widen this stop, lower
that target, or skip.

## Install

```
pip install -r requirements.txt
```

Python 3.11+. Dependencies: numpy, scipy, requests, click, rich, pytest.

## Use

### Mode 1 — pre-trade analysis

```
python -m trader_edge.cli analyze RELIANCE 2850 3000 2800 --days 5 --qty 10
```

Output:

```
RELIANCE long bracket — ₹2850.00 -> target ₹3000.00, stop ₹2800.00, 5d
  NOISE STOP CHECK
    Realized vol (ann.):   22.1%
    P(stop hit by noise):  58%
    Noise-safe stop:       ₹2758.46 (~30% noise hit)

  OPTIONS-CHAIN ORACLE  (expiry 2026-06-03)
    ATM IV:                22.0%
    P(touch target):       9%
    P(touch stop):         58%

  WHO HITS FIRST  (Monte Carlo at implied vol)
    P(target first):       8%
    P(stop first):         52%

  EXPECTED VALUE
    Headline R:R:          3.00:1
    True R:R (joint):      0.46:1
    Net EV (real-world):   ₹-17.42/share

ALTERNATIVES
  1. Widen stop to ₹2758.50  -> EV ₹-13.69
  2. Realistic target ₹2925   -> EV ₹-3.67
  3. Skip the trade
```

### Mode 2 — trade journal

Score recent trades and surface behavioral leaks:

```
python -m trader_edge.cli journal --days 30
```

### Inspecting the option chain

```
python -m trader_edge.cli chain RELIANCE
```

## Connecting your Groww account

By default the CLI uses a deterministic mock provider. To use live data:

1. Generate an access token from your Groww developer console.
2. Set the env var:

   ```powershell
   $env:GROWW_ACCESS_TOKEN = "your_token_here"
   ```

3. Pass `--provider groww` (or just leave `--provider auto` — it will use
   Groww if the token is set).

Endpoints called (read-only):
- `GET /v1/live-data/ltp`
- `GET /v1/historical/candle/range`
- `GET /v1/live-data/option-chain`
- `GET /v1/order/list`

The client is **read-only by design**. Order placement is intentionally
not exposed.

## Architecture

```
trader_edge/
  math_core/
    volatility.py     # close-to-close, Parkinson, Garman-Klass, EWMA
    black_scholes.py  # pricing, Greeks, IV inversion (Newton + bisection)
    barrier.py        # reflection principle + Monte Carlo joint barriers
    implied_pdf.py    # Breeden-Litzenberger, IV smile fit, prob extraction
    ev.py             # expected value with brokerage + slippage
  api/
    base.py           # DataProvider abstract interface
    models.py         # Candle, OptionChain, Order
    groww_client.py   # live REST client
    mock_provider.py  # offline demo provider
  analysis/
    pretrade.py       # mode 1 orchestration
    suggestions.py    # alternative trade structures
    journal.py        # mode 2: pair orders, compute leaks
  cli.py              # click entry points
tests/                # pytest, 31 tests covering math correctness
```

## The math, in one paragraph each

**Reflection principle.** For arithmetic Brownian motion `X_t` with drift `m`
and vol `σ`, the probability that `min X_t ≤ a` over `[0, T]` is
`Φ((a - mT)/(σ√T)) + exp(2ma/σ²) · Φ((a + mT)/(σ√T))`. We apply it to
`log(S_t/S_0)` with drift `(μ - σ²/2)`. The closed form is exact; tests
verify it against a Brownian-bridge-corrected Monte Carlo to within 2.5%.

**Breeden-Litzenberger.** The risk-neutral terminal-price PDF is
`f(K) = e^{rT} · ∂²C/∂K²`. We fit a quadratic IV smile in log-moneyness from
the chain, reprice calls on a dense even-spaced grid, take a central-difference
2nd derivative, clip negatives (numerical noise), and renormalize.

**IV inversion.** Newton-Raphson on Black-Scholes vega, with bisection
fallback on the no-arbitrage interval. Tested for round-trip exactness on
calls and puts across moneyness.

**Variance risk premium.** Implied vol embeds a premium over realized;
typically 3-5 vol points for indices. We subtract this to convert
risk-neutral probabilities to a real-world approximation, and report both
side-by-side so you can judge the disagreement.

## Testing

```
python -m pytest -q
```

31 tests, ~6s runtime. Math correctness is verified against:
- Monte Carlo with Brownian-bridge correction (barrier formula)
- Round-trip BS pricing/IV inversion
- Synthetic GBM paths (volatility estimators)
- Hand-computed expected values (EV)

## What this is not

- Not a signal generator. It evaluates *your* trade idea, not its own.
- Not an order placement tool. Read-only by design.
- Not financial advice.
- Not predictive of any single trade outcome — probabilities are
  distributions, not certainties.

## What's next (if you extend it)

- SVI parametrization for the IV smile (better extrapolation outside listed strikes)
- Multi-expiry term structure (currently uses nearest expiry only)
- Spreads and other multi-leg structures (currently single-leg cash + option suggestion)
- Real-time WebSocket feed (currently REST polling)
- Portfolio-level Greeks aggregation across open positions

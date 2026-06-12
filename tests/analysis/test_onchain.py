"""
Tests for OnChainScorer, WhaleTracker, ExchangeFlowAnalyzer.

Covers whale accumulation/distribution, exchange flow signals, and
edge cases with None/empty metrics.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.analysis.onchain.exchange_flow import ExchangeFlowAnalyzer, ExchangeFlowMetrics
from src.analysis.onchain.scorer import OnChainScore, OnChainScorer
from src.analysis.onchain.whale_tracker import WhaleMetrics, WhaleTracker, WhaleTransaction

# ── Helpers ──────────────────────────────────────────────────────────────────


def _whale_metrics(
    symbol: str = "BTC",
    whale_confidence: float = 0.0,
    accumulation_score: float = 50.0,
    distribution_score: float = 50.0,
    large_tx: int = 0,
    volume_24h: float = 0.0,
    net_exchange_flow_24h: float = 0.0,
) -> WhaleMetrics:
    return WhaleMetrics(
        symbol=symbol,
        large_transactions_24h=large_tx,
        total_volume_24h=volume_24h,
        net_exchange_flow_24h=net_exchange_flow_24h,
        whale_confidence=whale_confidence,
        accumulation_score=accumulation_score,
        distribution_score=distribution_score,
    )


def _exchange_metrics(
    symbol: str = "BTC",
    inflow: float = 0.0,
    outflow: float = 0.0,
    inflow_outflow_ratio: float = 1.0,
    reserve: float | None = None,
) -> ExchangeFlowMetrics:
    net_flow = inflow - outflow
    return ExchangeFlowMetrics(
        symbol=symbol,
        inflow_24h=inflow,
        outflow_24h=outflow,
        net_flow_24h=net_flow,
        inflow_7d=inflow * 7,
        outflow_7d=outflow * 7,
        net_flow_7d=(inflow - outflow) * 7,
        inflow_outflow_ratio=inflow_outflow_ratio,
        exchange_reserve=reserve or 0,
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestOnChainScorer:
    """Tests for OnChainScorer scoring logic."""

    def test_whale_accumulation_bullish_score(self) -> None:
        """Whale accumulation (high accumulation score, +ve confidence) → bullish."""
        scorer = OnChainScorer()
        wm = _whale_metrics(
            whale_confidence=0.6,
            accumulation_score=80.0,
            distribution_score=20.0,
            volume_24h=100_000_000,
            large_tx=30,
        )
        em = _exchange_metrics(inflow=5_000_000, outflow=5_000_000)
        score = scorer.compute_score("BTC", whale_metrics=wm, exchange_metrics=em)

        assert score.direction == "bullish"
        assert score.whale_score > 60
        assert score.total_score > 55

    def test_no_metrics_returns_neutral_score_50(self) -> None:
        """When no metrics are provided, direction should be neutral with score=50."""
        scorer = OnChainScorer()
        score = scorer.compute_score("BTC", whale_metrics=None, exchange_metrics=None)

        assert score.direction == "neutral"
        assert score.total_score == 50.0
        assert score.whale_score == 50.0
        assert score.exchange_flow_score == 50.0

    def test_whale_distribution_bearish(self) -> None:
        """Whale distribution (high distribution, -ve confidence) → bearish."""
        scorer = OnChainScorer()
        wm = _whale_metrics(
            whale_confidence=-0.5,
            accumulation_score=20.0,
            distribution_score=80.0,
        )
        em = _exchange_metrics(inflow=5_000_000, outflow=5_000_000)
        score = scorer.compute_score("BTC", whale_metrics=wm, exchange_metrics=em)

        assert score.direction == "bearish"
        assert score.whale_score < 40

    def test_exchange_outflows_bullish(self) -> None:
        """Strong exchange outflows (net negative flow) → bullish signal."""
        scorer = OnChainScorer()
        wm = _whale_metrics()
        # $5M outflow → net_flow = -5_000_000
        em = _exchange_metrics(outflow=6_000_000, inflow=1_000_000)
        score = scorer.compute_score("BTC", whale_metrics=wm, exchange_metrics=em)

        assert score.exchange_flow_score > 55
        assert "bullish" in score.direction or "neutral" in score.direction

    def test_exchange_inflows_bearish(self) -> None:
        """Strong exchange inflows (net positive flow) → bearish signal."""
        scorer = OnChainScorer()
        wm = _whale_metrics()
        em = _exchange_metrics(inflow=6_000_000, outflow=1_000_000)
        score = scorer.compute_score("BTC", whale_metrics=wm, exchange_metrics=em)

        assert score.exchange_flow_score < 45

    def test_compute_score_returns_on_chain_score_instance(self) -> None:
        """compute_score returns a properly typed OnChainScore."""
        scorer = OnChainScorer()
        wm = _whale_metrics()
        em = _exchange_metrics()
        score = scorer.compute_score("ETH", whale_metrics=wm, exchange_metrics=em)

        assert isinstance(score, OnChainScore)
        assert score.symbol == "ETH"
        assert hasattr(score, "key_signals")
        assert hasattr(score, "warnings")

    def test_key_signals_present_with_metrics(self) -> None:
        """Scorer produces key signals when whale/exchange metrics are provided."""
        scorer = OnChainScorer()
        wm = _whale_metrics(
            accumulation_score=75.0,
            whale_confidence=0.5,
        )
        em = _exchange_metrics(outflow=8_000_000, inflow=2_000_000)
        score = scorer.compute_score("BTC", whale_metrics=wm, exchange_metrics=em)

        assert len(score.key_signals) > 0


class TestWhaleTracker:
    """Tests for WhaleTracker record/query logic."""

    def test_get_metrics_returns_none_for_unknown_symbol(self) -> None:
        """get_metrics on an untouched symbol should return None."""
        tracker = WhaleTracker()
        metrics = tracker.get_metrics("UNKNOWN")
        assert metrics is None

    def test_record_and_compute_metrics(self) -> None:
        """Recording whale transactions and computing metrics works end-to-end."""
        tracker = WhaleTracker()
        now = datetime.now(UTC).timestamp()

        txs = [
            WhaleTransaction(
                tx_hash="tx1",
                symbol="BTC",
                value_usd=2_000_000,
                from_address="0xwhale1",
                to_address="0xexchange1",
                transaction_type="exchange_in",
                timestamp=now - 3600,
            ),
            WhaleTransaction(
                tx_hash="tx2",
                symbol="BTC",
                value_usd=3_000_000,
                from_address="0xexchange1",
                to_address="0xwhale2",
                transaction_type="exchange_out",
                timestamp=now - 7200,
            ),
        ]
        tracker.record_batch(txs)
        metrics = tracker.compute_metrics("BTC")

        assert metrics.symbol == "BTC"
        assert metrics.large_transactions_24h == 2
        assert metrics.total_volume_24h == 5_000_000
        # exchange_in (2M) - exchange_out (3M) = -1M
        assert metrics.net_exchange_flow_24h == -1_000_000

    def test_whale_signal_accumulation(self) -> None:
        """get_whale_signal returns 'bullish' on accumulation."""
        tracker = WhaleTracker()
        now = datetime.now(UTC).timestamp()

        txs = [
            WhaleTransaction(
                tx_hash="tx1", symbol="BTC", value_usd=5_000_000,
                from_address="0xexchange", to_address="0xwhale",
                transaction_type="exchange_out", timestamp=now - 1800,
            ),
            WhaleTransaction(
                tx_hash="tx2", symbol="BTC", value_usd=4_000_000,
                from_address="0xexchange", to_address="0xwhale2",
                transaction_type="exchange_out", timestamp=now - 900,
            ),
        ]
        tracker.record_batch(txs)
        tracker.compute_metrics("BTC")
        signal = tracker.get_whale_signal("BTC")
        assert signal == "bullish"


class TestExchangeFlowAnalyzer:
    """Tests for ExchangeFlowAnalyzer analysis logic."""

    def test_analyze_returns_metrics(self) -> None:
        """analyze() returns a well-formed ExchangeFlowMetrics object."""
        analyzer = ExchangeFlowAnalyzer()
        metrics = analyzer.analyze("BTC", inflow_24h=10_000_000, outflow_24h=5_000_000)

        assert isinstance(metrics, ExchangeFlowMetrics)
        assert metrics.symbol == "BTC"
        assert metrics.inflow_24h == 10_000_000
        assert metrics.outflow_24h == 5_000_000
        assert metrics.net_flow_24h == 5_000_000
        assert metrics.inflow_outflow_ratio == 2.0

    def test_net_flow_direction_outflow(self) -> None:
        """Net negative flow (more outflow than inflow) → 'outflow' perception, bullish."""
        analyzer = ExchangeFlowAnalyzer()
        metrics = analyzer.analyze("ETH", inflow_24h=1_000_000, outflow_24h=8_000_000)

        assert metrics.net_flow_24h < 0
        assert metrics.signal == "bullish"

    def test_net_flow_direction_inflow(self) -> None:
        """Net positive flow (more inflow than outflow) → bearish signal."""
        analyzer = ExchangeFlowAnalyzer()
        metrics = analyzer.analyze("ETH", inflow_24h=8_000_000, outflow_24h=1_000_000)

        assert metrics.net_flow_24h > 0
        assert metrics.signal == "bearish"

    def test_get_metrics_returns_cached(self) -> None:
        """get_metrics returns the last analyzed metrics."""
        analyzer = ExchangeFlowAnalyzer()
        metrics = analyzer.analyze("BTC", inflow_24h=5_000_000, outflow_24h=5_000_000)
        cached = analyzer.get_metrics("BTC")
        assert cached is not None
        assert cached is metrics

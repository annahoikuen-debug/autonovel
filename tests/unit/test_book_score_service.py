"""Backward-compatible test runner for BookScoreCalculator.

Delegates to tests/unit/services/test_book_score_calculator.py.
"""

from tests.unit.services.test_book_score_calculator import (  # noqa: F401
    TestBookScoreCalculatorInit,
    TestBookScoreCalculatorReport,
    TestBookScoreCalculatorSaveAndGet,
    TestBookScoreCalculatorSpecialists,
    TestBookScoreCalculatorWeights,
    TestBookScoreDataclass,
)

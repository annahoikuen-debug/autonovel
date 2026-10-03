"""narrative_balancer の Earley パーサー / 逐次パーサーの単体テスト。

conftest が ortools 未導入時に特定キーワードを含むパスを収集から除外するため、
モジュールは importlib で関数内インポートする。
"""
from __future__ import annotations

import importlib



def _incremental():
    return importlib.import_module("src.narrative_balancer.grammar.incremental")


def _parser():
    return importlib.import_module("src.narrative_balancer.grammar.parser")


def _symbols():
    return importlib.import_module("src.narrative_balancer.grammar.symbols")


def _forest():
    return importlib.import_module("src.narrative_balancer.grammar.parse_forest")


class TestEarleyItem:
    def test_next_symbol_and_completed(self):
        NT, T = _symbols().NonTerminal, _symbols().Terminal
        item = _forest().EarleyItem(lhs=NT.STORY, rule=(T.SETUP, NT.QUARTER), dot=0, origin=0)
        assert item.next_symbol is T.SETUP
        assert item.is_completed is False
        done = _forest().EarleyItem(lhs=NT.STORY, rule=(T.SETUP,), dot=1, origin=0)
        assert done.next_symbol is None
        assert done.is_completed is True

    def test_hashable(self):
        NT, T = _symbols().NonTerminal, _symbols().Terminal
        a = _forest().EarleyItem(lhs=NT.STORY, rule=(T.SETUP,), dot=0, origin=0)
        b = _forest().EarleyItem(lhs=NT.STORY, rule=(T.SETUP,), dot=0, origin=0)
        assert a == b
        assert len({a, b}) == 1


class TestEarleyParser:
    def test_empty_prefix_is_valid(self):
        p = _parser().EarleyParser()
        forest = p.parse_prefix([])
        assert forest.consumed_terminals == 0
        assert forest.is_valid_prefix is True
        assert len(forest.chart) == 1

    def test_valid_prefix_pending_terminal_only(self):
        T = _symbols().Terminal
        forest = _parser().EarleyParser().parse_prefix([T.SETUP])
        assert forest.consumed_terminals == 1
        assert forest.is_valid_prefix is True
        # chart[1] の全 item が終端を次に持つため pending 非終端は無い
        assert forest.pending_nonterminals == set()

    def test_pending_nonterminal_before_first_terminal(self):
        NT, T = _symbols().NonTerminal, _symbols().Terminal
        grammar = {NT.STORY: [(NT.QUARTER, T.CLIMAX)], NT.QUARTER: [(T.SETUP, T.RISING)]}
        forest = _parser().EarleyParser(grammar=grammar).parse_prefix([])
        assert forest.pending_nonterminals == {NT.QUARTER}

    def test_full_sequence_completes(self):
        T = _symbols().Terminal
        p = _parser().EarleyParser()
        forest = p.parse_prefix([T.SETUP, T.RISING, T.BATTLE, T.PAYOFF])
        assert forest.is_valid_prefix is True
        assert forest.completed_nonterminals

    def test_custom_start_symbol(self):
        NT, T = _symbols().NonTerminal, _symbols().Terminal
        p = _parser().EarleyParser(start_symbol=NT.QUARTER)
        forest = p.parse_prefix([T.SETUP])
        assert forest.consumed_terminals == 1
        assert forest.is_valid_prefix is True

    def test_grammar_defaults_when_empty_dict(self):
        # grammar={} は falsy なので既定 GRAMMAR が使われる
        forest = _parser().EarleyParser(grammar={}).parse_prefix(
            [_symbols().Terminal.SETUP]
        )
        assert forest.is_valid_prefix is True
        assert len(forest.chart) == 2

    def test_custom_grammar_prediction_and_scan(self):
        NT, T = _symbols().NonTerminal, _symbols().Terminal
        grammar = {NT.STORY: [(NT.QUARTER, T.CLIMAX)], NT.QUARTER: [(T.SETUP,)]}
        forest = _parser().EarleyParser(grammar=grammar).parse_prefix([T.SETUP])
        assert forest.completed_nonterminals == {NT.QUARTER}
        assert forest.is_valid_prefix is True

    def test_completion_advances_parent(self):
        NT, T = _symbols().NonTerminal, _symbols().Terminal
        grammar = {NT.STORY: [(NT.QUARTER, T.CLIMAX)], NT.QUARTER: [(T.SETUP,)]}
        forest = _parser().EarleyParser(grammar=grammar).parse_prefix([T.SETUP, T.CLIMAX])
        assert NT.STORY in forest.completed_nonterminals
        assert forest.is_valid_prefix is True

    def test_unmatched_terminal_gives_empty_last_chart(self):
        NT, T = _symbols().NonTerminal, _symbols().Terminal
        grammar = {NT.STORY: [(NT.QUARTER,)], NT.QUARTER: [(T.SETUP,)]}
        forest = _parser().EarleyParser(grammar=grammar).parse_prefix([T.RISING])
        assert forest.chart[-1] == set()
        assert forest.is_valid_prefix is False

    def test_max_items_pruning_does_not_crash(self):
        p = _parser().EarleyParser(max_items_per_chart=1)
        forest = p.parse_prefix(
            [_symbols().Terminal.SETUP, _symbols().Terminal.RISING]
        )
        assert forest.consumed_terminals == 2


class TestIncrementalParser:
    def test_creates_default_parser(self):
        inc = _incremental().IncrementalParser()
        assert inc.current_terminals == []
        assert inc.current_forest is None
        assert isinstance(inc.parser, _parser().EarleyParser)

    def test_accepts_injected_parser(self):
        p = _parser().EarleyParser()
        assert _incremental().IncrementalParser(p).parser is p

    def test_add_terminal_updates_forest(self):
        T = _symbols().Terminal
        inc = _incremental().IncrementalParser()
        forest = inc.add_terminal(T.SETUP)
        assert forest.consumed_terminals == 1
        assert inc.current_forest is forest
        assert inc.current_terminals == [T.SETUP]

    def test_add_multiple_terminals(self):
        T = _symbols().Terminal
        inc = _incremental().IncrementalParser()
        inc.add_terminal(T.SETUP)
        forest = inc.add_terminal(T.RISING)
        assert forest.consumed_terminals == 2
        assert len(inc.current_terminals) == 2

    def test_reset(self):
        T = _symbols().Terminal
        inc = _incremental().IncrementalParser()
        inc.add_terminal(T.SETUP)
        inc.reset()
        assert inc.current_terminals == []
        assert inc.current_forest is None

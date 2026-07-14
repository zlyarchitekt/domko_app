"""Kernel optymalizacji (plan 2026-07-14, Etap 1) -- kontrakty testowane na
syntetycznym generatorze liczbowym, bez geometrii."""

import random

from services.optimize import Budget, Candidate, dedupe_and_rank, pick_best, run_random_search


class _NumberGenerator:
    """Genome = float z [0, 10); build = identyczność; mutacja = +-0.5."""

    def random_genome(self, rng: random.Random) -> float:
        return rng.uniform(0.0, 10.0)

    def mutate(self, genome: float, rng: random.Random) -> float:
        return genome + rng.uniform(-0.5, 0.5)

    def build(self, genome: float) -> float:
        return genome


def _evaluator(genome: float, payload: float):
    # cel: genome == 3.0; hard-invalid powyżej 8
    score = abs(payload - 3.0)
    violations = ["za duże"] if payload > 8.0 else []
    return score, {"dist": score}, violations


def test_random_search_deterministic_and_budgeted():
    gen = _NumberGenerator()
    a = run_random_search(gen, _evaluator, Budget(evaluations=12))
    b = run_random_search(gen, _evaluator, Budget(evaluations=12))
    assert len(a) == 12
    assert [c.genome for c in a] == [c.genome for c in b]
    assert all(isinstance(c, Candidate) for c in a)
    assert all(c.hard_valid == (not c.hard_violations) for c in a)


def test_pick_best_prefers_hard_valid():
    cands = [
        Candidate(genome=9.0, payload=9.0, score=0.1, components={}, hard_valid=False, hard_violations=["x"]),
        Candidate(genome=4.0, payload=4.0, score=1.0, components={}, hard_valid=True, hard_violations=[]),
    ]
    assert pick_best(cands).genome == 4.0
    # wszystkie invalid -> najniższy score
    all_bad = [
        Candidate(genome=9.0, payload=9.0, score=0.5, components={}, hard_valid=False, hard_violations=["x"]),
        Candidate(genome=8.5, payload=8.5, score=0.2, components={}, hard_valid=False, hard_violations=["x"]),
    ]
    assert pick_best(all_bad).genome == 8.5


def test_dedupe_and_rank():
    mk = lambda g, s, ok: Candidate(genome=g, payload=g, score=s, components={}, hard_valid=ok,
                                    hard_violations=[] if ok else ["x"])
    cands = [mk(1.0, 0.9, True), mk(1.0, 0.9, True), mk(2.0, 0.1, False), mk(3.0, 0.5, True)]
    ranked = dedupe_and_rank(cands, limit=10)
    assert [c.genome for c in ranked] == [3.0, 1.0, 2.0]  # valid-first, potem score; duplikat 1.0 odpada
    assert len(dedupe_and_rank(cands, limit=2)) == 2

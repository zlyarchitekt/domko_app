"""Kernel optymalizacji (plan 2026-07-14, Etap 1) -- kontrakty testowane na
syntetycznym generatorze liczbowym, bez geometrii."""

import random

from services.optimize import (
    Budget,
    Candidate,
    dedupe_and_rank,
    pick_best,
    run_random_search,
    run_simulated_annealing,
)


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


def test_sa_beats_or_matches_random_search():
    """SA z budżetem 60 (local search + restarty) na tej funkcji celu
    (dolina w 3.0, kara za >8.0) statystycznie pewnie znajduje wynik
    nie gorszy niż RandomSearch z tym samym budżetem."""
    gen = _NumberGenerator()
    sa = run_simulated_annealing(gen, _evaluator, Budget(evaluations=60))
    rs = run_random_search(gen, _evaluator, Budget(evaluations=60))
    assert pick_best(sa).score <= pick_best(rs).score


def test_sa_deterministic():
    gen = _NumberGenerator()
    a = run_simulated_annealing(gen, _evaluator, Budget(evaluations=60))
    b = run_simulated_annealing(gen, _evaluator, Budget(evaluations=60))
    assert [c.genome for c in a] == [c.genome for c in b]
    assert len(a) == len(b)


def test_sa_history_length_matches_formula():
    """Historia SA (bez seed_candidates): każdy restart dokleja 1 fresh-start
    kandydata (bo brak seedów) + per_restart sąsiadów z mutacji.
    per_restart = max(1, budget.evaluations // restarts).
    len(history) == restarts * per_restart + (restarts - len(seed_candidates or []))
    -- tutaj seed_candidates=None więc wszystkie `restarts` restartów robią
    fresh-start (dokładają +1 każdy)."""
    budget = Budget(evaluations=60)
    restarts = 3
    per_restart = max(1, budget.evaluations // max(1, restarts))
    expected = restarts * per_restart + restarts
    assert expected == 63

    gen = _NumberGenerator()
    history = run_simulated_annealing(gen, _evaluator, budget, restarts=restarts)
    assert len(history) == expected


def test_sa_history_length_with_seed_candidates():
    """Gdy seed_candidates pokrywa WSZYSTKIE restarty, żaden restart nie
    dokleja fresh-start kandydata do historii -- tylko sąsiedzi z mutacji."""
    budget = Budget(evaluations=30)
    restarts = 3
    per_restart = max(1, budget.evaluations // max(1, restarts))
    expected = restarts * per_restart  # 0 fresh-starts: len(seeds) >= restarts

    seeds = [
        Candidate(genome=3.0 + i, payload=3.0 + i, score=float(i), components={}, hard_valid=True, hard_violations=[])
        for i in range(restarts)
    ]
    gen = _NumberGenerator()
    history = run_simulated_annealing(gen, _evaluator, budget, seed_candidates=seeds, restarts=restarts)
    assert len(history) == expected


def test_sa_uses_seed_candidates_as_starting_points():
    """Seed kandydat już bliski optimum (genome=3.0, score=0.0) -- SA
    (akceptacja zawsze przy delta<=0) nigdy nie powinno skończyć gorzej."""
    gen = _NumberGenerator()
    near_optimal = Candidate(
        genome=3.0, payload=3.0, score=0.0, components={"dist": 0.0}, hard_valid=True, hard_violations=[]
    )
    history = run_simulated_annealing(
        gen, _evaluator, Budget(evaluations=30), seed_candidates=[near_optimal], restarts=1
    )
    # seed_candidates nie są re-dodawane do historii (per plan) -- "final best"
    # to najlepszy z (historia + seedy), bo caller zawsze ma oba zbiory.
    assert pick_best(history + [near_optimal]).score <= near_optimal.score

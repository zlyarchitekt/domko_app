"""Kernel optymalizacji (plan 2026-07-14): generator / ewaluator / strategia.

Generator buduje kandydata z genomu i jest poprawny KONSTRUKCYJNIE (np. krajacz
traktowy: mieszkanie zawsze korytarz->elewacja). Ewaluator to czysta funkcja
(genome, payload) -> (score, components, hard_violations). Strategia decyduje,
które genomy próbować w ramach budżetu. Etap 1: RandomSearch (zachowanie 1:1 ze
starą pętlą `for seed in range(N)`); Etap 2 doda SimulatedAnnealing; Etap 3
NSGA-II. Determinizm: wyłącznie random.Random(seed) pochodne od indeksu."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass
class Candidate:
    genome: Any
    payload: Any
    score: float
    components: dict = field(default_factory=dict)
    hard_valid: bool = True
    hard_violations: list = field(default_factory=list)


@dataclass
class Budget:
    evaluations: int


class Generator(Protocol):
    def random_genome(self, rng: random.Random) -> Any: ...
    def mutate(self, genome: Any, rng: random.Random) -> Any: ...
    def build(self, genome: Any) -> Any: ...


Evaluator = Callable[[Any, Any], "tuple[float, dict, list]"]


def evaluate_genome(generator: Generator, evaluator: Evaluator, genome: Any) -> Candidate:
    payload = generator.build(genome)
    score, components, violations = evaluator(genome, payload)
    return Candidate(genome=genome, payload=payload, score=score, components=components,
                     hard_valid=not violations, hard_violations=list(violations))


def run_random_search(generator: Generator, evaluator: Evaluator, budget: Budget) -> list[Candidate]:
    out: list[Candidate] = []
    for i in range(budget.evaluations):
        rng = random.Random(i)
        out.append(evaluate_genome(generator, evaluator, generator.random_genome(rng)))
    return out


def pick_best(candidates: list[Candidate]) -> Candidate:
    """Najniższy score wśród spełniających zakazy; fallback najniższy w ogóle
    (ta sama reguła co unit_mix.pick_best_iteration)."""
    valid = [c for c in candidates if c.hard_valid]
    pool = valid or candidates
    return min(pool, key=lambda c: c.score)


def dedupe_and_rank(candidates: list[Candidate], limit: int) -> list[Candidate]:
    """Unikalne po genomie, ważne przed łamiącymi zakazy, w grupach po score."""
    seen: set = set()
    unique: list[Candidate] = []
    for c in candidates:
        key = c.genome if isinstance(c.genome, (int, float, str, tuple)) else repr(c.genome)
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    unique.sort(key=lambda c: (0 if c.hard_valid else 1, c.score))
    return unique[:limit]


def run_simulated_annealing(
    generator: Generator,
    evaluator: Evaluator,
    budget: Budget,
    seed_candidates: "list[Candidate] | None" = None,
    restarts: int = 3,
) -> list[Candidate]:
    """SA z restartami: budżet dzielony po równo między restarty; każdy restart
    startuje z kolejnego najlepszego seed-kandydata (albo losowego genomu).
    Temperatura: T0 = max(1e-6, 0.25 * score startu), wykładniczo do ~T0/100.
    Akceptacja: lepszy zawsze; gorszy z p = exp(-delta/T). Kandydat łamiący
    zakazy dostaje score + 1.0 kary do porównań SA (ale w historii zostaje
    z prawdziwym score) -- SA szuka w stronę ważnych, nie przez nie."""
    history: list[Candidate] = []
    seeds = list(seed_candidates or [])
    per_restart = max(1, budget.evaluations // max(1, restarts))
    for r in range(restarts):
        rng = random.Random(10_000 + r)
        if r < len(seeds):
            current = seeds[r]
        else:
            current = evaluate_genome(generator, evaluator, generator.random_genome(rng))
            history.append(current)

        def eff(c: Candidate) -> float:
            return c.score + (0.0 if c.hard_valid else 1.0)

        t = max(1e-6, 0.25 * eff(current))
        cooling = (0.01) ** (1.0 / max(1, per_restart))
        for _ in range(per_restart):
            neighbor = evaluate_genome(generator, evaluator, generator.mutate(current.genome, rng))
            history.append(neighbor)
            delta = eff(neighbor) - eff(current)
            if delta <= 0 or rng.random() < math.exp(-delta / t):
                current = neighbor
            t *= cooling
    return history

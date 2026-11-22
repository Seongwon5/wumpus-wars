"""시안 2 (unified) 시험: 누구나 캐고 싸운다. 광부는 이동 + 행동, 궁수는 맨해튼 3 사격."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wumpus.api import (ATTACK_DAMAGE, HP_UNIFIED, CARRY, ARCHER, EXPLORER, CAMP, Move, Mine, Attack,  # noqa: E402
                        sight_cells)
from wumpus.engine import Game  # noqa: E402
from wumpus.maps import GameMap  # noqa: E402


def src(body):
    return 'from wumpus.api import *\ndef turn(me, view, memory):\n    ' + body + '\n'


IDLE = src('return None')


def blank(w=20, h=20, walls=(), ore=None):
    return GameMap(w, h, 'H', set(walls), dict(ore or {}), set(), [(2, 2), (w - 3, 2)], 0, 'test')


def game(gmap, s0=IDLE, s1=IDLE):
    g = Game(gmap, [s0, s1], ['a', 'b'], rules={'unified': True})
    for u in list(g.units):
        g.at.pop((u.x, u.y), None)
    g.units = []
    return g


def put(g, team, kind, x, y):
    u = g._new_unit(team, kind, x, y)
    g.units.append(u)
    return u


def test_unified_hp_and_carry():
    g = game(blank())
    m, a = put(g, 0, EXPLORER, 5, 5), put(g, 0, ARCHER, 7, 5)
    assert m.hp == HP_UNIFIED[EXPLORER] == 12 and a.hp == HP_UNIFIED[ARCHER] == 8
    assert CARRY[EXPLORER] == 5 and CARRY[ARCHER] == 2


def test_miner_moves_then_attacks_same_turn():
    g = game(blank(), src("return Move('E'), Attack(me.x + 2, me.y)"))
    m = put(g, 0, EXPLORER, 5, 5)
    e = put(g, 1, ARCHER, 7, 5)
    g._take_turn(m)
    assert (m.x, m.y) == (6, 5) and e.hp == HP_UNIFIED[ARCHER] - ATTACK_DAMAGE


def test_miner_moves_then_mines_same_turn():
    g = game(blank(ore={(6, 5): 3}), src("return Move('E'), Mine()"))
    m = put(g, 0, EXPLORER, 5, 5)
    g._take_turn(m)
    assert (m.x, m.y) == (6, 5) and m.carry == 1


def test_archer_only_first_action():
    g = game(blank(), src("return Move('E'), Attack(me.x + 3, me.y)"))
    a = put(g, 0, ARCHER, 5, 5)
    e = put(g, 1, EXPLORER, 9, 5)
    g._take_turn(a)
    assert (a.x, a.y) == (6, 5) and e.hp == HP_UNIFIED[EXPLORER]


def test_miner_melee_only_adjacent():
    g = game(blank())
    m = put(g, 0, EXPLORER, 5, 5)
    e = put(g, 1, EXPLORER, 6, 6)                  # 대각선: 맨해튼 2
    g._apply(m, Attack(6, 6))
    assert e.hp == HP_UNIFIED[EXPLORER]


def test_archer_manhattan_three_and_diagonal():
    g = game(blank())
    a = put(g, 0, ARCHER, 5, 5)
    near = put(g, 1, EXPLORER, 7, 6)               # 맨해튼 3: 맞음
    far = put(g, 1, EXPLORER, 7, 7)                # 맨해튼 4: 안 닿음
    g._apply(a, Attack(7, 6))
    g._apply(a, Attack(7, 7))
    assert near.hp == HP_UNIFIED[EXPLORER] - ATTACK_DAMAGE and far.hp == HP_UNIFIED[EXPLORER]


def test_wall_blocks_archer_sight():
    g = game(blank(walls={(6, 5)}))
    a = put(g, 0, ARCHER, 5, 5)
    e = put(g, 1, EXPLORER, 8, 5)
    g._apply(a, Attack(8, 5))
    assert e.hp == HP_UNIFIED[EXPLORER] and (6, 5) in sight_cells(5, 5, 8, 5)


def test_camp_only_from_adjacent():
    g = game(blank())
    a = put(g, 0, ARCHER, 15, 2)                   # 적 야영지 (17,2) 에서 2칸
    g._apply(a, Attack(17, 2))
    assert g.bases[1].hp == HP_UNIFIED[CAMP]
    g.at.pop((15, 2)); a.x = 16; g.at[(16, 2)] = a
    g._apply(a, Attack(17, 2))
    assert g.bases[1].hp == HP_UNIFIED[CAMP] - ATTACK_DAMAGE


def test_archer_mines_up_to_two():
    g = game(blank(ore={(5, 5): 9}))
    a = put(g, 0, ARCHER, 5, 5)
    for _ in range(4):
        g._apply(a, Mine())
    assert a.carry == CARRY[ARCHER]


def test_dead_unit_drops_all_gold():
    g = game(blank())
    a = put(g, 0, ARCHER, 5, 5)
    e = put(g, 1, EXPLORER, 7, 5)
    e.carry, e.hp = 5, 3
    g._apply(a, Attack(7, 5))
    assert not e.alive and g.loot[(7, 5)] == 5


def test_logic_bot_plays_unified_match():
    from wumpus.engine import run_match
    from wumpus.maps import generate
    r = run_match(generate(3), ['logic', 'logic'], seed=1)
    kinds = {e[0] for fr in r['frames'] for e in fr['e']}
    assert r['const']['rules']['unified'] and 'atk' in kinds and 'mine' in kinds

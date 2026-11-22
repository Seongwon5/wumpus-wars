"""시안 규칙 (fun-rules) 시험: 직선 화살, 화살 수, 횃불, 밀치기, 떨어진 금, 웜퍼스와 악취."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wumpus.api import ARROWS_MAX, ATTACK_DAMAGE, HP, WUMPUS_HP, WUMPUS_HOARD, ARCHER, EXPLORER  # noqa: E402
from wumpus.engine import Game, Unit, wumpus_cells  # noqa: E402
from wumpus.maps import GameMap, load_map  # noqa: E402

IDLE = 'def turn(me, view, memory):\n    return None\n'


def blank(w=20, h=20, traps=(), wumpus=None):
    m = GameMap(w, h, 'H', set(), {}, set(traps), [(2, 2), (w - 3, 2)], 0, 'test')
    if wumpus is not None:
        m.wumpus = wumpus
    return m


def game(gmap, src0=IDLE, src1=IDLE, **rules):
    g = Game(gmap, [src0, src1], ['a', 'b'], rules=rules or None)
    for u in list(g.units):                     # 처음 탐험가는 치운다 (장면을 손으로 만든다)
        g.at.pop((u.x, u.y), None)
    g.units = []
    return g


def put(g, team, kind, x, y):
    u = g._new_unit(team, kind, x, y)
    g.units.append(u)
    return u


def act(g, u, a):
    g._apply(u, a)


def test_line_shot_hits_first_unit_in_row():
    from wumpus.api import Shoot
    g = game(blank())
    a = put(g, 0, ARCHER, 5, 10)
    e = put(g, 1, EXPLORER, 9, 10)
    act(g, a, Shoot('E'))
    assert e.hp == HP[EXPLORER] - ATTACK_DAMAGE
    assert a.arrows == ARROWS_MAX - 1


def test_line_shot_misses_diagonal_and_out_of_range():
    from wumpus.api import Shoot, Attack
    g = game(blank())
    a = put(g, 0, ARCHER, 5, 10)
    d = put(g, 1, EXPLORER, 6, 11)              # 대각선 옆: 화살 줄 밖
    far = put(g, 1, EXPLORER, 11, 10)           # 6칸: 사거리 밖
    act(g, a, Attack(6, 11))
    act(g, a, Shoot('E'))
    assert d.hp == HP[EXPLORER] and far.hp == HP[EXPLORER]


def test_friendly_blocks_arrow():
    from wumpus.api import Shoot
    g = game(blank())
    a = put(g, 0, ARCHER, 5, 10)
    f = put(g, 0, EXPLORER, 6, 10)
    e = put(g, 1, EXPLORER, 8, 10)
    act(g, a, Shoot('E'))
    assert f.hp == HP[EXPLORER] and e.hp == HP[EXPLORER]


def test_arrows_run_out_and_refill_at_camp():
    from wumpus.api import Shoot
    g = game(blank())
    a = put(g, 0, ARCHER, 3, 3)                 # 야영지 (2,2) 옆
    e = put(g, 1, ARCHER, 3, 7)
    for _ in range(ARROWS_MAX + 1):
        act(g, a, Shoot('S'))
    assert a.arrows == 0 and e.hp == HP[ARCHER] - ATTACK_DAMAGE * ARROWS_MAX
    g._take_turn(a)                             # 차례 끝: 야영지 옆이므로 다시 가득
    assert a.arrows == ARROWS_MAX


def test_torch_on_adjacent_enemy_camp_uses_no_arrow():
    from wumpus.api import Shoot
    g = game(blank())
    a = put(g, 0, ARCHER, 16, 2)                # 적 야영지 (17,2) 바로 옆
    a.arrows = 0
    act(g, a, Shoot('E'))
    assert g.bases[1].hp == HP['camp'] - ATTACK_DAMAGE and a.arrows == 0


def test_push_into_pit_kills_and_reveals():
    from wumpus.api import Push
    g = game(blank(traps=[(8, 10)]))
    p = put(g, 0, EXPLORER, 6, 10)
    t = put(g, 1, ARCHER, 7, 10)
    act(g, p, Push('E'))
    assert not t.alive and (8, 10) in g.revealed


def test_push_blocked_by_wall_or_unit_does_nothing():
    from wumpus.api import Push
    m = blank()
    m.walls.add((8, 10))
    g = game(m)
    p = put(g, 0, EXPLORER, 6, 10)
    t = put(g, 1, ARCHER, 7, 10)
    act(g, p, Push('E'))
    assert (t.x, t.y) == (7, 10) and t.alive


def test_push_ignores_friends_and_camps():
    from wumpus.api import Push
    g = game(blank())
    p = put(g, 0, EXPLORER, 16, 3)
    f = put(g, 0, EXPLORER, 15, 3)
    act(g, p, Push('W'))
    act(g, p, Push('N'))                        # (16,2) 은 빈 칸, 적 야영지는 (17,2)
    assert (f.x, f.y) == (15, 3) and g.bases[1].hp == HP['camp']


def test_killed_unit_drops_gold_and_archer_picks_up_two():
    from wumpus.api import Shoot, Mine
    g = game(blank())
    a = put(g, 0, ARCHER, 5, 10)
    e = put(g, 1, EXPLORER, 6, 10)
    e.carry, e.hp = 4, 3
    act(g, a, Shoot('E'))
    assert not e.alive and g.loot[(6, 10)] == 4
    g.at.pop((5, 10)); a.x = 6; g.at[(6, 10)] = a
    act(g, a, Mine())
    assert a.carry == 2 and g.loot[(6, 10)] == 2


def test_pit_swallows_carried_gold():
    from wumpus.api import Move
    g = game(blank(traps=[(7, 10)]))
    e = put(g, 0, EXPLORER, 6, 10)
    e.carry = 5
    act(g, e, Move('E'))
    assert not e.alive and not g.loot


def test_wumpus_eats_walker_and_stench_around():
    from wumpus.api import Move
    g = game(blank(wumpus=[(10, 10)]))
    e = put(g, 0, EXPLORER, 9, 10)
    assert g.stench_at(9, 10) and not g.stench_at(8, 10) and not g.stench_at(9, 9)
    act(g, e, Move('E'))
    assert not e.alive


def test_wumpus_killed_by_three_arrows_screams_and_drops_hoard():
    from wumpus.api import Shoot
    g = game(blank(wumpus=[(10, 10)]))
    a = put(g, 0, ARCHER, 10, 6)
    for _ in range(WUMPUS_HP // ATTACK_DAMAGE):
        act(g, a, Shoot('S'))
    assert g.wumpus[(10, 10)] == 0 and g.screams == 1 and g.loot[(10, 10)] == WUMPUS_HOARD
    assert not g.stench_at(10, 9)


def test_wumpus_placement_is_symmetric_and_far_from_camps():
    for name in ('temple_gate', 'twin_pillars', 'scarab_maze'):
        m = load_map(name)
        cs = wumpus_cells(m)
        assert cs
        from wumpus.api import mirror, cheb, WUMPUS_CLEAR
        for c in cs:
            assert mirror(m.sym, c[0], c[1], m.w, m.h) in cs
            assert all(cheb(c[0], c[1], bx, by) > WUMPUS_CLEAR for bx, by in m.bases)
            assert c not in m.walls and c not in m.traps and c not in m.ore


def test_old_rules_switch_restores_adjacent_attack():
    from wumpus.api import Attack
    off = dict(line_shot=False, arrows=False, push=False, loot=False, wumpus=False)
    g = game(blank(), **off)
    a = put(g, 0, ARCHER, 5, 10)
    e = put(g, 1, EXPLORER, 6, 11)
    act(g, a, Attack(6, 11))
    assert e.hp == HP[EXPLORER] - ATTACK_DAMAGE and not g.wumpus

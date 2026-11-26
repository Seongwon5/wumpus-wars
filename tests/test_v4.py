"""시안 4 (v4) 시험: 금 재생 30 라운드 · 절반까지, 짐 10, 처치 금, 웜퍼스 체력 6 · 보물 30, 모험가 화살 한 발."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wumpus.api import (EXPLORER, Shoot, Attack, V4_CARRY, V4_KILL_GOLD, V4_WUMPUS_HP, V4_WUMPUS_HOARD,  # noqa: E402
                        V4_ARROW_DMG, V4_REGROW_EVERY, AGENT_HP)
from wumpus.engine import Game  # noqa: E402
from wumpus.maps import GameMap  # noqa: E402


def src(body):
    return 'from wumpus.api import *\ndef turn(me, view, memory):\n    ' + body + '\n'


IDLE = src('return None')


def blank(w=20, h=20, walls=(), ore=None, wumpus=None):
    m = GameMap(w, h, 'H', set(walls), dict(ore or {}), set(), [(2, 2), (w - 3, 2)], 0, 'test')
    m.wumpus = list(wumpus or [(10, 15)])
    return m


def game(gmap, s0=IDLE, s1=IDLE, v4=True):
    g = Game(gmap, [s0, s1], ['a', 'b'], rules={'agent': True, 'v4': v4})
    for u in list(g.units):
        g.at.pop((u.x, u.y), None)
    g.units = []
    return g


def put(g, team, x, y):
    u = g._new_unit(team, EXPLORER, x, y)
    g.units.append(u)
    return u


def test_v4_off_keeps_old_numbers():
    g = game(blank(), v4=False)
    u = put(g, 0, 5, 5)
    assert g.CAP[EXPLORER] == 5 and g.WHP == 9 and u.arrows == 0


def test_v4_numbers():
    g = game(blank())
    u = put(g, 0, 5, 5)
    assert g.CAP[EXPLORER] == V4_CARRY >= 10 ** 6 and g.WHP == V4_WUMPUS_HP == 6 and u.arrows == 1
    assert g.REGROW == V4_REGROW_EVERY == 30


def test_arrow_kills_wumpus_far_away_and_shooter_carries_hoard():
    g = game(blank(wumpus=[(10, 15)]), src("return Shoot('S')"))
    u = put(g, 0, 10, 5)
    s0 = g.screams
    g._take_turn(u)
    assert g.wumpus[(10, 15)] == 0 and g.screams == s0 + 1 and (10, 15) not in g.loot
    assert u.carry == V4_WUMPUS_HOARD and g.score[0] == 0      # 쏜 모험가가 즉시 든다 (바쳐야 점수)
    assert u.arrows == 0
    assert any(e[0] == 'arrow' and e[4:7] == [10, 15, 'w'] for e in g.events)


def test_arrow_stops_at_wall():
    g = game(blank(walls=[(10, 9)], wumpus=[(10, 15)]), src("return Shoot('S')"))
    u = put(g, 0, 10, 5)
    g._take_turn(u)
    assert g.wumpus[(10, 15)] == V4_WUMPUS_HP and u.arrows == 0
    assert any(e[0] == 'arrow' and e[4:6] == [10, 8] for e in g.events)


def test_arrow_hits_first_unit_even_teammate():
    g = game(blank(), src("return Shoot('E')"))
    u = put(g, 0, 5, 5)
    mate = put(g, 0, 8, 5)
    foe = put(g, 1, 12, 5)
    g._take_turn(u)
    assert mate.hp == AGENT_HP - V4_ARROW_DMG and foe.hp == AGENT_HP


def test_no_second_arrow_until_refill():
    g = game(blank(wumpus=[(10, 15)]), src("return Shoot('S')"))
    u = put(g, 0, 10, 5)
    g._take_turn(u)
    g.wumpus[(10, 15)] = V4_WUMPUS_HP
    g._take_turn(u)
    assert g.wumpus[(10, 15)] == V4_WUMPUS_HP


def test_refill_next_to_camp():
    g = game(blank())
    u = put(g, 0, 3, 2)                          # 야영지 (2,2) 옆
    u.arrows = 0
    g._take_turn(u)
    assert u.arrows == 1


def test_kill_gold_goes_to_killer():
    g = game(blank(), src("return Attack(me.x + 1, me.y)"))
    k = put(g, 0, 5, 5)
    v = put(g, 1, 6, 5)
    v.hp, v.carry = 3, 4
    g._take_turn(k)
    assert not v.alive and k.carry == 4 + V4_KILL_GOLD and g.loot.get((6, 5), 0) == 0


def test_kill_gold_no_cap():
    g = game(blank(), src("return Attack(me.x + 1, me.y)"))
    k = put(g, 0, 5, 5)
    v = put(g, 1, 6, 5)
    k.carry, v.hp, v.carry = 40, 3, 25
    g._take_turn(k)
    assert k.carry == 40 + 25 + V4_KILL_GOLD and g.loot.get((6, 5), 0) == 0     # 짐 상한 없음: 모두 쓰러뜨린 모험가에게


def test_mining_has_no_cap():
    g = game(blank(ore={(5, 5): 15}), src("return Mine()"))
    u = put(g, 0, 5, 5)
    u.carry = 30
    g._take_turn(u)
    assert u.carry == 31


def test_sword_does_nothing_to_wumpus():
    g = game(blank(wumpus=[(10, 15)]), src("return Attack(10, 15)"))
    u = put(g, 0, 10, 14)
    for _ in range(3):
        g._take_turn(u)
    g._wumpus_phase(1)
    assert g.wumpus[(10, 15)] == V4_WUMPUS_HP and u.hp == AGENT_HP      # 웜퍼스는 화살로만, 깨어나 반격하지도 않는다


def test_walking_into_wumpus_kills_and_gold_vanishes():
    g = game(blank(wumpus=[(10, 15)]), src("return Move('S')"))
    u = put(g, 0, 10, 14)
    u.carry = 7
    g._take_turn(u)
    assert not u.alive and not g.loot


def test_pit_death_gold_vanishes():
    m = blank()
    m.traps = {(6, 5)}
    g = game(m, src("return Move('E')"))
    u = put(g, 0, 5, 5)
    u.carry = 9
    g._take_turn(u)
    assert not u.alive and not g.loot


def test_camp_kill_pays_team():
    g = game(blank())
    v = put(g, 1, 3, 3)                          # 붉은 야영지 (2,2) 옆
    v.hp, v.carry = 1, 12
    s0 = g.score[0]
    g._take_turn(g.bases[0])
    assert not v.alive and g.score[0] == s0 + 12 + V4_KILL_GOLD and not g.loot


def test_teammate_arrow_kill_gives_gold_without_bounty():
    g = game(blank(), src("return Shoot('E')"))
    u = put(g, 0, 5, 5)
    mate = put(g, 0, 8, 5)
    mate.hp, mate.carry = 4, 10
    g._take_turn(u)
    assert not mate.alive and u.carry == 10 and not g.loot


def test_gold_chain_new_site_after_depletion():
    g = game(blank(ore={(9, 9): 1, (10, 9): 1}), src("return Mine()"))
    assert g.vein_next.get((9, 9)) is not None
    u = put(g, 0, 9, 9)
    g._take_turn(u)
    n = g.vein_next[(9, 9)]
    assert (9, 9) not in g.ore and g.ore[n] == 1 and g.grow[n] == g.vein_cap[n] == 1
    assert any(e[0] == 'vein' and (e[1], e[2]) == n for e in g.events)


def test_gold_chain_symmetric_and_safe():
    from wumpus.maps import generate
    from wumpus.engine import gold_chains, wumpus_cells
    from wumpus.api import mirror
    gm = generate(123)
    nxt, cap = gold_chains(gm, set(wumpus_cells(gm)))
    assert nxt
    for a, b in nxt.items():
        ma, mb = mirror(gm.sym, a[0], a[1], gm.w, gm.h), mirror(gm.sym, b[0], b[1], gm.w, gm.h)
        assert nxt.get(ma) == mb
        assert b not in gm.walls and b not in gm.traps and b not in gm.ore


def test_arrow_damages_enemy_camp_far_away():
    g = game(blank(w=30), src("return Shoot('E')"))
    u = put(g, 0, 5, 2)                          # 붉은 야영지 (2,2) 동쪽, 푸른 야영지 (27,2) 까지 일직선
    hp0 = g.bases[1].hp
    g._take_turn(u)
    assert g.bases[1].hp == hp0 - V4_ARROW_DMG


def test_arrow_blocked_by_own_camp():
    g = game(blank(), src("return Shoot('W')"))
    u = put(g, 0, 5, 2)
    hp0 = g.bases[0].hp
    g._take_turn(u)
    assert g.bases[0].hp == hp0 and u.arrows == 0


def test_v4_cost_and_start_bank():
    from wumpus.api import V4_COST, V4_START_BANK, Spawn
    g = game(blank())
    assert g.bank == [V4_START_BANK, V4_START_BANK] and g.COST[EXPLORER] == V4_COST == 20
    g2 = game(blank(), src("return Spawn('explorer', 'E')"))
    g2.bank[0] = 19
    g2.codes[0] = None
    camp = g2.bases[0]
    g2._apply(camp, Spawn('explorer', 'E'))
    assert g2.bank[0] == 19 and len(g2.units) == 0                  # 19 로는 못 뽑는다
    g2.bank[0] = 20
    g2._apply(camp, Spawn('explorer', 'E'))
    assert g2.bank[0] == 0 and len(g2.units) == 1


def test_v4_no_starting_units():
    g = Game(blank(), [IDLE, IDLE], ['a', 'b'], rules={'agent': True, 'v4': True})
    assert len(g.units) == 0 and g.bank == [20, 20]
    g0 = Game(blank(), [IDLE, IDLE], ['a', 'b'], rules={'agent': True, 'v4': False})
    assert len(g0.units) == 4                                     # 지금 규칙은 팀마다 둘

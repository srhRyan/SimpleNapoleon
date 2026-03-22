"""
Game logger — dumps all 4 review pages as text files after each game.

Files written to logs/ directory:
  {timestamp}_{winner}_summary.txt   — game result + settings
  {timestamp}_{winner}_initial.txt   — initial hands + bottom cards
  {timestamp}_{winner}_starting.txt  — post-swap hands + discarded cards
  {timestamp}_{winner}_rounds.txt    — all 25 rounds with card plays
"""

import os
from datetime import datetime

SUIT_SYM = {'spades': 'S', 'hearts': 'H', 'diamonds': 'D', 'clubs': 'C'}
SUIT_NAME = {'spades': 'Spades', 'hearts': 'Hearts', 'diamonds': 'Diamonds', 'clubs': 'Clubs'}
JOKER_NAME = {
    'big1': 'BigJoker1', 'big2': 'BigJoker2',
    'mid1': 'MidJoker1', 'mid2': 'MidJoker2',
    'small1': 'SmallJoker1', 'small2': 'SmallJoker2',
}
ROLE_LABEL = {'napoleon': 'Napoleon', 'secretary': 'Secretary', 'united_nations': 'UN'}
POINT_RANKS = {'J', 'Q', 'K', 'A'}


def _card_str(c):
    if c.get('is_joker') or c.get('suit') == 'joker':
        return JOKER_NAME.get(c['rank'], c['rank'])
    return f"{SUIT_SYM.get(c['suit'], '?')}{c['rank']}"


def _cards_str(cards, trump_suit=None):
    """Format a list of card dicts sorted display."""
    parts = []
    for c in cards:
        s = _card_str(c)
        if c.get('is_point') or (not c.get('is_joker') and c.get('rank') in POINT_RANKS):
            s += '*'
        parts.append(s)
    return ' '.join(parts)


def _hand_stats(cards, trump_suit):
    jokers = [c for c in cards if c.get('is_joker') or c.get('suit') == 'joker']
    suits = {}
    for c in cards:
        if c.get('is_joker') or c.get('suit') == 'joker':
            continue
        s = c['suit']
        if s not in suits:
            suits[s] = {'count': 0, 'pts': 0}
        suits[s]['count'] += 1
        if c.get('rank') in POINT_RANKS:
            suits[s]['pts'] += 1
    order = [trump_suit] + [s for s in ['spades', 'hearts', 'diamonds', 'clubs'] if s != trump_suit]
    parts = []
    if jokers:
        parts.append(f"Joker:{len(jokers)}")
    for s in order:
        if s not in suits:
            parts.append(f"{SUIT_SYM.get(s,'?')}:VOID")
            continue
        si = suits[s]
        label = f"{SUIT_SYM.get(s,'?')}:{si['count']}"
        if si['pts']:
            label += f"({si['pts']}pt)"
        if s == trump_suit:
            label += '[T]'
        parts.append(label)
    total_pts = sum(1 for c in cards if not (c.get('is_joker') or c.get('suit') == 'joker')
                    and c.get('rank') in POINT_RANKS)
    parts.append(f"Total:{len(cards)}({total_pts}pt)")
    return '  '.join(parts)


def dump_game_log(state, log_dir='logs'):
    """Write all 4 review pages as text files. Called when game finishes."""
    os.makedirs(log_dir, exist_ok=True)
    replay = state.get('replay')
    if not replay:
        return

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    winner = state.get('winner', 'unknown')
    prefix = os.path.join(log_dir, f"{ts}_{winner}")

    players = state['players']
    trump = state['trump_suit']
    trump_label = f"{SUIT_SYM.get(trump, '?')} {SUIT_NAME.get(trump, trump)}"
    sec_card = state.get('secretary_card', {})
    sec_label = _card_str(sec_card) if sec_card.get('suit') else '?'
    nap_idx = state['napoleon_idx']
    sec_indices = state.get('secretary_indices', [])

    # ---- Summary ----
    lines = []
    lines.append(f"=== Napoleon Game Log ===")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Winner: {winner.upper()}")
    lines.append(f"Napoleon: P{nap_idx} ({players[nap_idx]['name']})")
    sec_names = ', '.join(f'P{i} ({players[i]["name"]})' for i in sec_indices) if sec_indices else 'None (solo)'
    lines.append(f"Secretary: {sec_names}")
    lines.append(f"Trump: {trump_label}")
    lines.append(f"Secretary Card: {sec_label}")
    lines.append(f"Contract: {state['contract_points']}")
    lines.append(f"Napoleon Team: {state['napoleon_points']} pts")
    lines.append(f"United Nations: {state['un_points']} pts")
    lines.append(f"")
    prof_abbr = {1: 'Bgn', 2: 'Cpt', 3: 'Exp'}
    strat_abbr = {'aggressive': 'Agg', 'conservative': 'Con', 'tactical': 'Tac', 'deceptive': 'Dec'}
    lines.append(f"--- Player Results ---")
    for p in players:
        role = ROLE_LABEL.get(p['role'], p['role'])
        strat = strat_abbr.get(p.get('ai_strategy', ''), p.get('ai_strategy', '?'))
        prof = prof_abbr.get(p.get('ai_level', 0), '?')
        lines.append(f"  P{p['index']} {p['name']:12s} {role:12s} {p['points_won']:3d} pts  [{strat}/{prof}]")

    # Bidding history
    bid_history = replay.get('bid_history', [])
    if bid_history:
        lines.append(f"")
        lines.append(f"--- Bidding ---")
        for entry in bid_history:
            pidx = entry['player']
            pname = players[pidx]['name'] if pidx < len(players) else '?'
            bid = entry['bid']
            if bid == 'pass':
                lines.append(f"  P{pidx} {pname:12s} Pass")
            else:
                lines.append(f"  P{pidx} {pname:12s} Bid {bid}")

    _write(f"{prefix}_summary.txt", lines)

    # ---- Initial Hands ----
    lines = []
    lines.append(f"=== Initial Hands (before swap) ===")
    lines.append(f"Trump: {trump_label}")
    lines.append(f"")
    lines.append(f"--- Bottom Cards (12) ---")
    bottom = replay.get('initial_bottom', [])
    lines.append(f"  {_cards_str(bottom)}")
    lines.append(f"  {_hand_stats(bottom, trump)}")
    lines.append(f"")
    for i, hand in enumerate(replay.get('initial_hands', [])):
        p = players[i]
        role = ROLE_LABEL.get(p['role'], '?')
        lines.append(f"--- P{i} {p['name']} ({role}) ---")
        lines.append(f"  {_cards_str(hand)}")
        lines.append(f"  {_hand_stats(hand, trump)}")
        lines.append(f"")
    _write(f"{prefix}_initial.txt", lines)

    # ---- Starting Hands (post-swap) ----
    lines = []
    lines.append(f"=== Starting Hands (after swap) ===")
    lines.append(f"Trump: {trump_label}")
    discarded = replay.get('discarded_cards', [])
    if discarded:
        disc_pts = sum(1 for c in discarded if c.get('rank') in POINT_RANKS and not c.get('is_joker'))
        lines.append(f"")
        lines.append(f"--- Discarded by Napoleon ({disc_pts} point cards -> UN) ---")
        lines.append(f"  {_cards_str(discarded)}")
    lines.append(f"")
    starting = replay.get('starting_hands', replay.get('initial_hands', []))
    for i, hand in enumerate(starting):
        p = players[i]
        role = ROLE_LABEL.get(p['role'], '?')
        lines.append(f"--- P{i} {p['name']} ({role}) [{len(hand)} cards] ---")
        lines.append(f"  {_cards_str(hand)}")
        lines.append(f"  {_hand_stats(hand, trump)}")
        lines.append(f"")
    _write(f"{prefix}_starting.txt", lines)

    # ---- All 25 Rounds ----
    lines = []
    lines.append(f"=== All 25 Rounds ===")
    lines.append(f"Trump: {trump_label}  |  Secretary Card: {sec_label}  |  Contract: {state['contract_points']}")
    lines.append(f"")

    # Header
    names = [f"P{p['index']}:{p['name']}" for p in players]
    role_icons = []
    for p in players:
        if p['role'] == 'napoleon':
            role_icons.append('[N]')
        elif p['role'] == 'secretary':
            role_icons.append('[S]')
        else:
            role_icons.append('[U]')
    header = f"{'Rnd':>4} {'Suit':>5}  " + '  '.join(f"{n+role_icons[i]:>16s}" for i, n in enumerate(names))
    header += f"  {'Pts':>4}  {'Score':>10}"
    lines.append(header)
    lines.append('-' * len(header))

    disc_pts = sum(1 for c in discarded if c.get('rank') in POINT_RANKS and not c.get('is_joker'))
    nap_run = 0
    un_run = disc_pts
    sec_revealed = False
    sec_accumulated = 0  # points secretary won while undercover

    if disc_pts > 0:
        row = f"{'--':>4} {'':>5}  " + '  '.join(f"{'':>16s}" for _ in range(6))
        row += f"  {'+' + str(disc_pts):>4}  {'N:0 U:' + str(disc_pts):>10}  discard"
        lines.append(row)

    tricks = replay.get('tricks', [])
    for ti, trick in enumerate(tricks):
        winner_idx = trick['winner']
        wp = players[winner_idx]
        w_role = wp['role']

        just_revealed = trick.get('secretary_revealed') and not sec_revealed
        sec_revealed = trick.get('secretary_revealed', sec_revealed)

        # On reveal: transfer secretary's accumulated points
        if just_revealed:
            nap_run += sec_accumulated
            un_run -= sec_accumulated

        is_nap_win = w_role == 'napoleon' or (w_role == 'secretary' and sec_revealed)

        if is_nap_win:
            nap_run += trick['points']
        else:
            un_run += trick['points']
            if w_role == 'secretary' and not sec_revealed:
                sec_accumulated += trick['points']

        lead_suit = trick.get('lead_suit', '')
        lead_sym = SUIT_SYM.get(lead_suit, '?')
        lead_card = trick['cards'][0][1] if trick['cards'] else None
        is_declared = lead_card and (lead_card.get('is_joker') or lead_card.get('suit') == 'joker')
        suit_col = lead_sym + ('*' if is_declared else ' ')

        # Build card by player
        card_by_p = {}
        for pidx, card in trick['cards']:
            card_by_p[pidx] = card

        cols = []
        for pi in range(6):
            c = card_by_p.get(pi)
            if not c:
                cols.append('')
                continue
            s = _card_str(c)
            marks = ''
            if pi == winner_idx:
                marks += ' WIN'
            if pi == trick.get('lead_player'):
                marks += ' (L)'
            is_sec = (sec_card.get('id') and c.get('id') == sec_card['id'])
            if is_sec:
                marks += ' SEC'
            cols.append(s + marks)

        pts_str = f"+{trick['points']}" if trick['points'] > 0 else '-'
        score_str = f"N:{nap_run} U:{un_run}"
        reveal_str = ' <<REVEAL>>' if just_revealed else ''

        row = f"R{trick['round']:>3} {suit_col:>5}  "
        row += '  '.join(f"{c:>16s}" for c in cols)
        row += f"  {pts_str:>4}  {score_str:>10}{reveal_str}"
        lines.append(row)

    lines.append(f"")
    lines.append(f"Final: Napoleon {nap_run} pts | UN {un_run} pts | Total {nap_run + un_run}")
    lines.append(f"Contract: {state['contract_points']} | Result: {winner.upper()}")
    _write(f"{prefix}_rounds.txt", lines)

    return prefix


def _write(path, lines):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

"""
AI players for Napoleon card game.

Strategy types:
  aggressive   — Big cards early, flush trumps, grab points ASAP.
  conservative — Save resources, play low, wait for guaranteed wins.
  tactical     — Adaptive balanced play, reads the table.
  deceptive    — Secretary hides longer, varies play to confuse.

Proficiency (1-3):
  1 — 25% random mistakes (beginner execution)
  2 — 10% random mistakes (competent)
  3 — 0% mistakes (perfect execution of strategy)
"""

import random
from .card import (
    Card, SUITS, RANKS, RANK_ORDER, POINT_RANKS, CALL_JOKER_MAP,
    JOKER_PRIORITY, sort_key,
)
from .engine import GameEngine, Phase, Role

# Proficiency -> chance of random play instead of strategy
MISTAKE_RATE = {1: 0.25, 2: 0.10, 3: 0.0}

# Strategy parameters
# All strategies share core competitive balance (joker threshold, feed, bid).
# Differences are in style: tempo, secretary timing, trump washing, void preference.
# Core competitive params are identical — strategies differ in style, not strength.
STRATEGY_PARAMS = {
    'aggressive': {
        'bid_bonus': 0,
        'joker_pt_threshold': 2,
        'void_max_pts': 2,       # sacrifice points for voids → more cuts
        'feed_eagerness': 0.8,
        'sec_reveal_pts': 3,
        'trump_wash_prob': 0.5,
    },
    'conservative': {
        'bid_bonus': 0,
        'joker_pt_threshold': 2,
        'void_max_pts': 0,       # keep all points, win by accumulation
        'feed_eagerness': 0.9,
        'sec_reveal_pts': 3,
        'trump_wash_prob': 0.5,
    },
    'tactical': {
        'bid_bonus': 0,
        'joker_pt_threshold': 2,
        'void_max_pts': 1,       # balanced void/point tradeoff
        'feed_eagerness': 0.8,
        'sec_reveal_pts': 3,
        'trump_wash_prob': 0.5,
    },
    'deceptive': {
        'bid_bonus': 0,
        'joker_pt_threshold': 2,
        'void_max_pts': 1,
        'feed_eagerness': 0.8,
        'sec_reveal_pts': 4,     # slightly longer hide
        'trump_wash_prob': 0.5,
    },
}


class AI:
    def __init__(self, engine: GameEngine):
        self.engine = engine

    def _params(self, player_idx):
        return STRATEGY_PARAMS[self.engine.players[player_idx].ai_strategy]

    def _should_mistake(self, player_idx):
        level = self.engine.players[player_idx].ai_level
        return random.random() < MISTAKE_RATE.get(level, 0)

    def _random_play(self, playable):
        """Mistake play — random but not catastrophically stupid.
        Excludes jokers and secretary cards (never waste those randomly)."""
        if not playable:
            return None
        safe = [c for c in playable if not c.is_joker and not self.engine._is_secretary_card(c)]
        pool = safe if safe else playable
        return random.choice(pool).id

    # ==================================================================
    # Bidding
    # ==================================================================
    def decide_bid(self, player_idx):
        p = self.engine.players[player_idx]
        hand = p.hand
        highest = self.engine.highest_bid
        params = self._params(player_idx)

        max_bid = self._estimate_hand(hand, params)
        if max_bid < 23:
            return 0
        min_bid = max(23, highest + 1)
        if min_bid > max_bid:
            return 0

        # Proficiency: low proficiency may pass even with a good hand
        if self._should_mistake(player_idx) and random.random() < 0.5:
            return 0

        room = max_bid - min_bid
        if room <= 0:
            return min_bid if random.random() < 0.6 else 0
        if highest == 0:
            bid = 23 + random.randint(0, min(room // 2, 2))
            return bid
        raise_amt = 1
        if room >= 3 and random.random() < 0.3:
            raise_amt = 2
        bid = min_bid + raise_amt - 1
        return bid if bid <= max_bid else min_bid

    def _estimate_hand(self, hand, params):
        suit_counts = {}
        for c in hand:
            if not c.is_joker:
                suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
        jokers = sum(1 for c in hand if c.is_joker)
        aces = sum(1 for c in hand if not c.is_joker and c.rank == 'A')
        kings = sum(1 for c in hand if not c.is_joker and c.rank == 'K')
        best_count = max(suit_counts.values()) if suit_counts else 0
        est = int(aces * 1.5 + kings * 0.8 + jokers * 2 + best_count * 0.4 + 16)
        est += params['bid_bonus'] + random.randint(-1, 1)
        return min(est, 30)

    # ==================================================================
    # Choose trump suit
    # ==================================================================
    def decide_trump(self, player_idx):
        hand = self.engine.players[player_idx].hand
        suit_counts = {}
        for c in hand:
            if not c.is_joker:
                suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
        return max(suit_counts, key=suit_counts.get) if suit_counts else 'spades'

    # ==================================================================
    # Swap cards (discard 12)
    # ==================================================================
    def decide_discard(self, player_idx):
        hand = list(self.engine.players[player_idx].hand) + list(self.engine.bottom_cards)
        trump = self.engine.trump_suit
        params = self._params(player_idx)
        max_void_pts = params['void_max_pts']

        keep = []
        side_suits = {}
        for c in hand:
            if c.is_joker or self.engine._is_secretary_card(c) or c.suit == trump:
                keep.append(c)
            elif c.rank == 'A':
                keep.append(c)
            else:
                side_suits.setdefault(c.suit, []).append(c)

        discard = []
        need = 12

        suit_evals = []
        for suit, cards in side_suits.items():
            pts = sum(1 for c in cards if c.is_point)
            suit_evals.append((suit, cards, len(cards), pts))
        suit_evals.sort(key=lambda x: (x[2], x[3]))

        # Phase 1: void suits within strategy's tolerance
        for suit, cards, count, pts in suit_evals:
            if len(discard) >= need:
                break
            remaining = need - len(discard)
            if count <= remaining and pts <= max_void_pts:
                discard.extend(cards)
                side_suits[suit] = []

        # Phase 2: discard non-point cards
        if len(discard) < need:
            pool = []
            for suit in side_suits:
                for c in side_suits[suit]:
                    if c not in discard and not c.is_point:
                        pool.append(c)
            pool.sort(key=lambda c: c.rank_value)
            for c in pool:
                if len(discard) >= need:
                    break
                discard.append(c)

        # Phase 3: void remaining suits all-or-nothing
        if len(discard) < need:
            remaining_suits = [(s, [c for c in cards if c not in discard])
                               for s, cards in side_suits.items()
                               if any(c not in discard for c in cards)]
            remaining_suits.sort(key=lambda x: len(x[1]))
            for suit, leftover in remaining_suits:
                if len(discard) >= need:
                    break
                if len(leftover) <= need - len(discard):
                    discard.extend(leftover)

        # Phase 4: last resort individual points
        if len(discard) < need:
            pts_left = []
            for suit in side_suits:
                for c in side_suits[suit]:
                    if c not in discard and c.is_point:
                        pts_left.append(c)
            pts_left.sort(key=lambda c: c.rank_value)
            for c in pts_left:
                if len(discard) >= need:
                    break
                discard.append(c)

        # Phase 5: fallback
        if len(discard) < need:
            keep.sort(key=lambda c: (c.is_joker, self.engine._is_secretary_card(c),
                                     c.rank == 'A', c.rank_value))
            for c in keep:
                if len(discard) >= need:
                    break
                discard.append(c)

        return [c.id for c in discard[:12]]

    # ==================================================================
    # Choose secretary card
    # ==================================================================
    def decide_secretary(self, player_idx):
        choices = self.engine.get_valid_secretary_choices()
        if not choices:
            hand = self.engine.players[player_idx].hand
            for c in hand:
                if c.is_joker:
                    return 'joker', c.rank
            return 'spades', 'A'

        hand = self.engine.players[player_idx].hand
        non_joker = [c for c in choices if c['suit'] != 'joker']
        joker_choices = [c for c in choices if c['suit'] == 'joker']

        candidates = []
        for ch in non_joker:
            our_count = sum(1 for c in hand if c.matches_type(ch['suit'], ch['rank']))
            others = 3 - our_count
            score = 10 if others == 1 else 5
            rank_prio = {'A': 4, 'K': 3, 'Q': 2, 'J': 1}.get(ch['rank'], 0)
            candidates.append((ch['suit'], ch['rank'], score, rank_prio))
        if candidates:
            candidates.sort(key=lambda x: (x[2], x[3]), reverse=True)
            return candidates[0][0], candidates[0][1]
        if joker_choices:
            return joker_choices[0]['suit'], joker_choices[0]['rank']
        return choices[0]['suit'], choices[0]['rank']

    # ==================================================================
    # Play a card
    # ==================================================================
    def decide_play(self, player_idx):
        playable = self.engine.get_playable_cards(player_idx)
        if not playable:
            hand = self.engine.players[player_idx].hand
            return hand[0].id if hand else None
        if len(playable) == 1:
            return playable[0].id

        # Proficiency: chance of random play
        if self._should_mistake(player_idx):
            return self._random_play(playable)

        p = self.engine.players[player_idx]
        strategy = p.ai_strategy
        role = p.role
        e = self.engine
        is_leading = len(e.current_trick) == 0
        params = STRATEGY_PARAMS[strategy]

        if role == Role.NAPOLEON:
            return self._play_napoleon(p, playable, is_leading, params)
        elif role == Role.SECRETARY:
            return self._play_secretary(p, playable, is_leading, params)
        else:
            return self._play_un(p, playable, is_leading, params)

    # ------------------------------------------------------------------
    # Napoleon
    # ------------------------------------------------------------------
    def _play_napoleon(self, player, playable, is_leading, params):
        e = self.engine
        if is_leading:
            return self._lead_for_points(player, playable, params)
        else:
            return self._follow_aggressive(player, playable, params)

    def _lead_for_points(self, player, playable, params):
        e = self.engine
        strategy = player.ai_strategy

        # Rounds 2-5: call joker with trump 3/9/6
        if 2 <= e.current_round <= 5:
            for rank in ['3', '9', '6']:
                for c in playable:
                    if not c.is_joker and c.suit == e.trump_suit and c.rank == rank:
                        return c.id

        side_aces = [c for c in playable if not c.is_joker and c.suit != e.trump_suit and c.rank == 'A']
        jokers = [c for c in playable if c.is_joker]
        trump_high = [c for c in playable if not c.is_joker and c.suit == e.trump_suit and c.rank in ('A', 'K')]
        side_kings = [c for c in playable if not c.is_joker and c.suit != e.trump_suit and c.rank == 'K']
        trump_other = [c for c in playable if not c.is_joker and c.suit == e.trump_suit and c.rank not in ('A', 'K')]

        my_trumps = sum(1 for c in player.hand if not c.is_joker and c.suit == e.trump_suit)
        played_trumps = self._count_played_suit(e.trump_suit)
        total_trumps = 3 * 13
        discarded_trumps = sum(1 for c in e.discarded_cards if not c.is_joker and c.suit == e.trump_suit)
        enemy_trumps = total_trumps - my_trumps - played_trumps - discarded_trumps

        # Core game theory lead order (shared by all strategies):
        # 1. Side aces (guaranteed points)
        # 2. Joker wash (drain enemy trumps, declare trump suit)
        # 3. Trump A/K (flush + points)
        # 4. Side kings (point grab)
        # 5. Remaining trumps
        # 6. Dump non-points
        #
        # Strategy differences are in FOLLOW play, bidding, and reveal timing.

        if side_aces:
            return side_aces[0].id
        if jokers and enemy_trumps > 3:
            jokers.sort(key=lambda c: c.joker_priority)
            return jokers[0].id
        if trump_high:
            trump_high.sort(key=lambda c: c.rank_value, reverse=True)
            return trump_high[0].id
        if side_kings:
            return side_kings[0].id
        if jokers:
            jokers.sort(key=lambda c: c.joker_priority)
            return jokers[0].id
        if trump_other:
            trump_other.sort(key=lambda c: c.rank_value, reverse=True)
            return trump_other[0].id

        non_point = [c for c in playable if not c.is_point]
        if non_point:
            non_point.sort(key=lambda c: c.rank_value)
            return non_point[0].id
        playable.sort(key=lambda c: c.rank_value)
        return playable[0].id

    # ------------------------------------------------------------------
    # Secretary
    # ------------------------------------------------------------------
    def _play_secretary(self, player, playable, is_leading, params):
        e = self.engine
        sec_cards = [c for c in playable if e._is_secretary_card(c)]
        non_sec = [c for c in playable if not e._is_secretary_card(c)]
        trick_points = sum(1 for _, c in e.current_trick if c.is_point)

        reveal_threshold = params['sec_reveal_pts']
        if not is_leading and sec_cards and e.current_trick:
            # Only reveal if ENEMY is winning — never beat Napoleon
            winner_idx = self._current_trick_winner()
            winner = e.players[winner_idx]
            napoleon_winning = (winner.role == Role.NAPOLEON)
            if not napoleon_winning:
                if trick_points >= reveal_threshold or (e.current_round >= 20 and trick_points >= 1):
                    return sec_cards[0].id

        if is_leading:
            if non_sec:
                if e.secretary_revealed:
                    # After reveal: lead aggressively
                    return self._lead_for_points(player, non_sec, params)
                else:
                    # Before reveal: lead like UN (conservative, don't risk point cards)
                    return self._lead_un_style(player, non_sec, params)
            return playable[0].id
        if non_sec:
            if e.secretary_revealed:
                return self._follow_aggressive(player, non_sec, params)
            else:
                return self._follow_un(player, non_sec, params)
        return playable[0].id

    def _is_dominant(self, card, player):
        """Check if card is the highest remaining in its suit (safe to lead)."""
        e = self.engine
        suit = card.suit
        rank_val = card.rank_value
        # Count how many cards with higher rank in same suit are accounted for
        # (played in tricks, discarded, or in own hand)
        higher_ranks = [r for r, v in RANK_ORDER.items() if v > rank_val]
        for hr in higher_ranks:
            # 3 copies total per suit+rank. How many accounted for?
            played = 0
            for trick in e.trick_history:
                cards = trick.get('cards', [])
                for _, cd in cards:
                    if cd.get('suit') == suit and cd.get('rank') == hr:
                        played += 1
            in_hand = sum(1 for c in player.hand if not c.is_joker and c.suit == suit and c.rank == hr)
            discarded = sum(1 for c in e.discarded_cards if not c.is_joker and c.suit == suit and c.rank == hr)
            if played + in_hand + discarded < 3:
                return False  # some higher cards still out there
        return True

    def _lead_un_style(self, player, playable, params):
        """Conservative lead for secretary (before reveal) or UN.
        Lead guaranteed winners or dominant cards. Otherwise lead low."""
        e = self.engine

        # Side aces — guaranteed winners
        side_aces = [c for c in playable if not c.is_joker and c.suit != e.trump_suit and c.rank == 'A']
        if side_aces:
            return side_aces[0].id

        # Dominant point cards (all higher cards accounted for) — safe to lead
        dominant_pts = [c for c in playable if not c.is_joker and c.suit != e.trump_suit
                        and c.is_point and self._is_dominant(c, player)]
        if dominant_pts:
            dominant_pts.sort(key=lambda c: c.rank_value, reverse=True)
            return dominant_pts[0].id

        # Lead from short side suits (low non-point cards to create voids)
        suit_counts = {}
        for c in player.hand:
            if not c.is_joker and c.suit != e.trump_suit:
                suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
        short = sorted([s for s in suit_counts if s != e.trump_suit],
                       key=lambda s: suit_counts[s])
        for s in short:
            cards = [c for c in playable if not c.is_joker and c.suit == s and not c.is_point]
            if cards:
                cards.sort(key=lambda c: c.rank_value)
                return cards[0].id

        # No safe low cards — lead lowest non-point
        non_point = [c for c in playable if not c.is_point and not c.is_joker]
        if non_point:
            non_point.sort(key=lambda c: c.rank_value)
            return non_point[0].id

        # Only point cards left — lead lowest (J first)
        playable.sort(key=lambda c: c.rank_value)
        return playable[0].id

    # ------------------------------------------------------------------
    # United Nations
    # ------------------------------------------------------------------
    def _play_un(self, player, playable, is_leading, params):
        e = self.engine
        non_joker = [c for c in playable if not c.is_joker]

        if is_leading:
            lead_from = non_joker if non_joker else playable

            if 2 <= e.current_round <= 5:
                trump_a = [c for c in lead_from if c.suit == e.trump_suit and c.rank == 'A']
                if trump_a:
                    return trump_a[0].id

            trumps = [c for c in lead_from if c.suit == e.trump_suit]
            if trumps and random.random() < params['trump_wash_prob']:
                trumps.sort(key=lambda c: c.rank_value, reverse=True)
                return trumps[0].id

            suit_counts = {}
            for c in player.hand:
                if not c.is_joker:
                    suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
            short = sorted([s for s in suit_counts if s != e.trump_suit],
                           key=lambda s: suit_counts[s])
            for s in short:
                cards = [c for c in lead_from if c.suit == s]
                if cards:
                    cards.sort(key=lambda c: c.rank_value)
                    return cards[0].id

            non_point = [c for c in lead_from if not c.is_point]
            if non_point:
                non_point.sort(key=lambda c: c.rank_value)
                return non_point[0].id
            if lead_from:
                return lead_from[0].id
            return playable[0].id
        else:
            return self._follow_un(player, playable, params)

    def _follow_un(self, player, playable, params):
        e = self.engine
        if not e.current_trick:
            # No cards on table yet — play lowest non-joker
            non_joker = [c for c in playable if not c.is_joker]
            return (non_joker[0].id if non_joker else playable[0].id)

        winner_idx = self._current_trick_winner()
        winner = e.players[winner_idx]
        trick_points = sum(1 for _, c in e.current_trick if c.is_point)
        winner_is_enemy = (winner.role == Role.NAPOLEON or
                          (winner.role == Role.SECRETARY and e.secretary_revealed))

        # Debug: log when joker would be played
        ally_winning = not winner_is_enemy
        if ally_winning:
            print(f'[AI-DEBUG] R{e.current_round} P{player.index} follow_un: ally P{winner_idx}({winner.role.value}) winning, trick_pts={trick_points}')

        if winner_is_enemy:
            best_prio = max(
                e._card_priority(c, i) for i, (_, c) in enumerate(e.current_trick)
            )
            play_pos = len(e.current_trick)
            beaters = [(e._card_priority(c, play_pos), c) for c in playable
                       if e._card_priority(c, play_pos) > best_prio]

            non_joker = [c for c in playable if not c.is_joker]
            has_lead = any(c.suit == e.lead_suit for c in non_joker)
            joker_threshold = params['joker_pt_threshold']

            if beaters:
                if trick_points >= 2:
                    beaters.sort(key=lambda x: x[0], reverse=True)
                    return beaters[0][1].id
                non_joker_beaters = [(p, c) for p, c in beaters if not c.is_joker]
                if non_joker_beaters:
                    if not has_lead:
                        trump_b = [(p, c) for p, c in non_joker_beaters if c.suit == e.trump_suit]
                        if trump_b:
                            trump_b.sort(key=lambda x: x[0])
                            return trump_b[0][1].id
                    non_joker_beaters.sort(key=lambda x: x[0])
                    return non_joker_beaters[0][1].id
                if trick_points >= joker_threshold:
                    beaters.sort(key=lambda x: x[0])
                    return beaters[0][1].id

            # Joker ambush — only if can actually win
            jokers = [c for c in playable if c.is_joker]
            if jokers and trick_points >= joker_threshold:
                winning_jokers = [j for j in jokers
                                  if e._card_priority(j, play_pos) > best_prio]
                if winning_jokers:
                    winning_jokers.sort(key=lambda c: c.joker_priority)
                    return winning_jokers[0].id

            if not has_lead:
                trumps = [c for c in non_joker if c.suit == e.trump_suit]
                if trumps:
                    trumps.sort(key=lambda c: c.rank_value)
                    return trumps[0].id

            dump = [c for c in non_joker if not c.is_point]
            if dump:
                dump.sort(key=lambda c: c.rank_value)
                return dump[0].id
            non_joker.sort(key=lambda c: c.rank_value)
            return non_joker[0].id if non_joker else playable[0].id
        else:
            # Ally winning — feed points
            feed = []
            for c in playable:
                if not c.is_point or c.is_joker or e._is_secretary_card(c):
                    continue
                if c.rank == 'A':
                    same_suit = sum(1 for x in player.hand if not x.is_joker and x.suit == c.suit)
                    if same_suit >= 2:
                        continue
                feed.append(c)
            if feed and random.random() < params['feed_eagerness']:
                feed.sort(key=lambda c: c.rank_value)
                return feed[0].id
            low = [c for c in playable if not c.is_joker and not e._is_secretary_card(c)
                   and not c.is_point]
            if low:
                low.sort(key=lambda c: c.rank_value)
                return low[0].id
            safe = [c for c in playable if not c.is_joker and not e._is_secretary_card(c)]
            if safe:
                safe.sort(key=lambda c: c.rank_value)
                return safe[0].id
            return playable[0].id

        # FINAL SAFETY: if we somehow reach here, never return joker when ally winning
        chosen_id = playable[0].id
        if ally_winning:
            non_joker = [c for c in playable if not c.is_joker]
            if non_joker:
                non_joker.sort(key=lambda c: c.rank_value)
                chosen_id = non_joker[0].id
        return chosen_id

    # ------------------------------------------------------------------
    # Shared: aggressive follow (Napoleon & Secretary)
    # ------------------------------------------------------------------
    def _follow_aggressive(self, player, playable, params):
        e = self.engine
        if not e.current_trick:
            playable.sort(key=lambda c: c.rank_value, reverse=True)
            return playable[0].id

        winner_idx = self._current_trick_winner()
        winner = e.players[winner_idx]
        trick_points = sum(1 for _, c in e.current_trick if c.is_point)

        my_role = player.role
        winner_is_ally = False
        if my_role == Role.NAPOLEON:
            winner_is_ally = (winner.role == Role.SECRETARY and e.secretary_revealed)
        elif my_role == Role.SECRETARY:
            winner_is_ally = (winner.role == Role.NAPOLEON)

        if winner_is_ally:
            feed = []
            for c in playable:
                if not c.is_point or c.is_joker or e._is_secretary_card(c):
                    continue
                if c.rank == 'A':
                    same_suit = sum(1 for x in player.hand if not x.is_joker and x.suit == c.suit)
                    if same_suit >= 2:
                        continue
                feed.append(c)
            if feed:
                feed.sort(key=lambda c: c.rank_value)
                return feed[0].id
            low = [c for c in playable if not c.is_point and not c.is_joker
                   and not e._is_secretary_card(c)]
            if low:
                low.sort(key=lambda c: c.rank_value)
                return low[0].id
            playable.sort(key=lambda c: c.rank_value)
            return playable[0].id

        # Enemy winning
        best_prio = max(
            e._card_priority(c, i) for i, (_, c) in enumerate(e.current_trick)
        )
        play_pos = len(e.current_trick)
        beaters = []
        for c in playable:
            p = e._card_priority(c, play_pos)
            if p > best_prio:
                beaters.append((p, c))

        has_lead_suit = any(not c.is_joker and c.suit == e.lead_suit
                           and not e._is_secretary_card(c) for c in playable)

        if beaters:
            # Void: cut with cheapest trump (not joker)
            if not has_lead_suit:
                trump_beaters = [(p, c) for p, c in beaters
                                 if not c.is_joker and c.suit == e.trump_suit]
                if trump_beaters:
                    trump_beaters.sort(key=lambda x: x[0])
                    return trump_beaters[0][1].id

            # Never waste joker on low-value tricks
            non_joker_beaters = [(p, c) for p, c in beaters if not c.is_joker]
            if trick_points >= 2:
                # High value — use strongest beater (including joker)
                beaters.sort(key=lambda x: x[0], reverse=True)
                return beaters[0][1].id
            else:
                # 0-1 points — only use non-joker beaters, save jokers
                if non_joker_beaters:
                    non_joker_beaters.sort(key=lambda x: x[0])
                    return non_joker_beaters[0][1].id
                # Only joker beaters on low-value trick — don't waste, dump instead

        non_point = [c for c in playable if not c.is_point and not c.is_joker
                     and not e._is_secretary_card(c)]
        if non_point:
            non_point.sort(key=lambda c: c.rank_value)
            return non_point[0].id
        playable.sort(key=lambda c: c.rank_value)
        return playable[0].id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _current_trick_winner(self):
        e = self.engine
        best_idx = e.current_trick[0][0]
        best_prio = e._card_priority(e.current_trick[0][1], 0)
        for i in range(1, len(e.current_trick)):
            prio = e._card_priority(e.current_trick[i][1], i)
            if prio > best_prio:
                best_prio = prio
                best_idx = e.current_trick[i][0]
        return best_idx

    def _count_played_suit(self, suit):
        count = 0
        for trick in self.engine.trick_history:
            cards = trick.get('cards', []) if isinstance(trick, dict) else trick
            for _, card_dict in cards:
                if card_dict.get('suit') == suit:
                    count += 1
        return count

    # ==================================================================
    # Choose lead suit (joker / secretary lead)
    # ==================================================================
    def decide_lead_suit(self, player_idx):
        e = self.engine
        player = e.players[player_idx]
        if player.ai_level == 1 and self._should_mistake(player_idx):
            return random.choice(SUITS)
        if player.role in (Role.NAPOLEON, Role.SECRETARY):
            return e.trump_suit
        suit_counts = {}
        for c in player.hand:
            if not c.is_joker and c.suit != e.trump_suit:
                suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
        if suit_counts:
            return max(suit_counts, key=suit_counts.get)
        return e.trump_suit

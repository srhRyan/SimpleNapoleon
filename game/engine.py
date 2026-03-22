import random
from enum import Enum
from .card import (
    Card, SUITS, RANKS, RANK_ORDER, CALL_JOKER_MAP, JOKER_PRIORITY,
    create_deck, shuffle_and_deal, sort_key,
)


MIN_BID = 23


class Phase(Enum):
    WAITING = 'waiting'
    BIDDING = 'bidding'
    CHOOSE_TRUMP = 'choose_trump'
    SWAP_CARDS = 'swap_cards'
    CHOOSE_SECRETARY = 'choose_secretary'
    ANNOUNCE = 'announce'
    PLAYING = 'playing'
    CHOOSE_LEAD_SUIT = 'choose_lead_suit'
    CHOOSE_CALL_JOKER = 'choose_call_joker'
    FINISHED = 'finished'


class Role(Enum):
    UNKNOWN = 'unknown'
    NAPOLEON = 'napoleon'
    SECRETARY = 'secretary'
    UNITED_NATIONS = 'united_nations'


STRATEGIES = ['aggressive', 'conservative', 'tactical', 'deceptive']


class Player:
    def __init__(self, index: int, name: str, is_ai: bool = False,
                 ai_level: int = 2, ai_strategy: str = 'tactical'):
        self.index = index
        self.name = name
        self.is_ai = is_ai
        self.ai_level = ai_level          # proficiency: 1-3
        self.ai_strategy = ai_strategy    # strategy type
        self.hand: list[Card] = []
        self.role = Role.UNKNOWN
        self.points_won = 0

    def to_dict(self, reveal_role=False, reveal_secretary=False) -> dict:
        role = self.role.value
        if self.role == Role.SECRETARY:
            if reveal_role:
                role = 'secretary'
            elif reveal_secretary:
                role = 'secretary'
            else:
                role = 'unknown'
        elif self.role == Role.UNITED_NATIONS and not reveal_role:
            role = 'unknown'
        return {
            'index': self.index,
            'name': self.name,
            'is_ai': self.is_ai,
            'hand_count': len(self.hand),
            'role': role,
            'points_won': self.points_won,
            'ai_level': self.ai_level,
            'ai_strategy': self.ai_strategy,
        }


class GameEngine:
    def __init__(self):
        self.reset()

    def reset(self):
        self.phase = Phase.WAITING
        self.players: list[Player] = []
        self.bottom_cards: list[Card] = []
        self.napoleon_idx = -1
        self.secretary_card_suit = ''
        self.secretary_card_rank = ''
        self.secretary_card_id = ''  # the specific card instance ID
        self.secretary_indices: list[int] = []
        self.trump_suit = ''
        self.initial_trump_suit = ''
        self.contract_points = 0
        self.current_round = 0
        self.current_trick: list[tuple[int, Card]] = []
        self.lead_suit = ''
        self.lead_player_idx = -1
        self.current_player_idx = -1
        self.napoleon_team_points = 0
        self.un_team_points = 0
        self.bid_history: list[dict] = []
        self.current_bidder_idx = -1
        self.highest_bid = 0
        self.highest_bidder_idx = -1
        self.consecutive_passes = 0
        self.forced_jokers: dict[int, Card] = {}
        self.last_trick_cards: list[tuple[int, Card]] = []
        self.last_trick_winner = -1
        self.last_trick_points = 0
        self.trick_history: list[list[tuple[int, dict]]] = []
        self.discarded_cards: list[Card] = []
        self.winner = ''
        self.trump_changed = False
        self.secretary_revealed = False

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def setup_players(self, human_name='Player', ai_levels=None, ai_strategies=None):
        if ai_levels is None:
            ai_levels = [2, 2, 2, 2, 2]
        if ai_strategies is None:
            ai_strategies = ['tactical'] * 5
        self.players = [Player(0, human_name, is_ai=False,
                               ai_level=ai_levels[0], ai_strategy=ai_strategies[0])]
        for i in range(5):
            self.players.append(Player(i + 1, f'AI-{i + 1}', is_ai=True,
                                       ai_level=ai_levels[i],
                                       ai_strategy=ai_strategies[i]))

    def start_game(self, saved_deal=None):
        if saved_deal:
            hands = saved_deal['hands']
            self.bottom_cards = saved_deal['bottom']
        else:
            deck = create_deck()
            hands, self.bottom_cards = shuffle_and_deal(deck)

        # Save raw cards for replay-same-game
        self._saved_deal = {
            'hands': [list(h) for h in hands],
            'bottom': list(self.bottom_cards),
        }

        for i, p in enumerate(self.players):
            p.hand = list(hands[i])
            p.role = Role.UNKNOWN
            p.points_won = 0

        # Store initial hands for review
        self.initial_hands = [[c.to_dict() for c in h] for h in hands]
        self.initial_bottom = [c.to_dict() for c in self.bottom_cards]

        self.phase = Phase.BIDDING
        self.current_round = 0
        self.napoleon_team_points = 0
        self.un_team_points = 0
        self.bid_history = []
        self.highest_bid = 0
        self.highest_bidder_idx = -1
        self.consecutive_passes = 0
        self.trick_history = []       # [{cards, winner, points, lead_suit, lead_player, round}]
        self.discarded_cards = []
        self.winner = ''
        self.trump_changed = False
        self.secretary_revealed = False
        self.current_bidder_idx = random.randint(0, 5)
        return self.current_bidder_idx

    # ------------------------------------------------------------------
    # Bidding  (counterclockwise, pass is temporary)
    # ------------------------------------------------------------------
    def place_bid(self, player_idx: int, bid: int = 0) -> tuple[bool, str]:
        if player_idx != self.current_bidder_idx:
            return False, 'not_your_turn'
        if bid == 0:
            self.consecutive_passes += 1
            self.bid_history.append({'player': player_idx, 'bid': 'pass'})
        else:
            min_bid = max(MIN_BID, self.highest_bid + 1)
            if bid < min_bid or bid > 48:
                return False, 'invalid_bid'
            self.highest_bid = bid
            self.highest_bidder_idx = player_idx
            self.consecutive_passes = 0
            self.bid_history.append({'player': player_idx, 'bid': bid})

        # End: someone bid and all 5 others passed consecutively
        if self.highest_bidder_idx >= 0 and self.consecutive_passes >= 5:
            self._become_napoleon()
            return True, 'bidding_complete'
        # End: nobody bid and all 6 passed consecutively
        if self.highest_bidder_idx < 0 and self.consecutive_passes >= 6:
            return True, 'all_passed'
        # Next bidder (counterclockwise)
        self.current_bidder_idx = (self.current_bidder_idx - 1) % 6
        return True, 'next_bid'

    def _become_napoleon(self):
        self.napoleon_idx = self.highest_bidder_idx
        self.contract_points = self.highest_bid
        self.players[self.napoleon_idx].role = Role.NAPOLEON
        self.phase = Phase.CHOOSE_TRUMP

    # ------------------------------------------------------------------
    # Pre-play
    # ------------------------------------------------------------------
    def choose_trump(self, suit: str) -> tuple[bool, str]:
        if suit not in SUITS:
            return False, 'invalid_suit'
        self.trump_suit = suit
        self.initial_trump_suit = suit
        self.phase = Phase.SWAP_CARDS
        return True, 'trump_chosen'

    def swap_cards(self, discard_ids: list[str]) -> tuple[bool, str]:
        nap = self.players[self.napoleon_idx]
        if len(discard_ids) != 12:
            return False, 'must_discard_12'
        nap.hand.extend(self.bottom_cards)
        discarded = []
        for cid in discard_ids:
            card = next((c for c in nap.hand if c.id == cid), None)
            if card is None:
                # rollback
                for c in discarded:
                    nap.hand.append(c)
                for c in self.bottom_cards:
                    if c in nap.hand:
                        nap.hand.remove(c)
                return False, 'card_not_found'
            nap.hand.remove(card)
            discarded.append(card)

        self.discarded_cards = discarded
        pts = sum(1 for c in discarded if c.is_point)
        if pts > 0:
            self.un_team_points += pts
        nap.hand.sort(key=sort_key)
        self.phase = Phase.CHOOSE_SECRETARY
        return True, 'cards_swapped'

    def change_trump(self, new_suit: str) -> tuple[bool, str]:
        if new_suit not in SUITS:
            return False, 'invalid_suit'
        if new_suit != self.initial_trump_suit and not self.trump_changed:
            self.contract_points += 3
            self.trump_suit = new_suit
            self.trump_changed = True
        return True, 'trump_changed'

    def choose_secretary(self, suit: str, rank: str) -> tuple[bool, str]:
        if suit == 'joker':
            if rank not in JOKER_PRIORITY:
                return False, 'invalid_joker'
        else:
            if suit not in SUITS or rank not in RANKS:
                return False, 'invalid_card'
            # Non-joker: Napoleon must hold >= 2 copies
            nap_hand = self.players[self.napoleon_idx].hand
            copies_in_hand = sum(1 for c in nap_hand if c.matches_type(suit, rank))
            if copies_in_hand < 2:
                return False, 'must_hold_2_copies'
        self.secretary_card_suit = suit
        self.secretary_card_rank = rank

        # Identify the ONE secretary — find first non-Napoleon player holding a copy
        self.secretary_indices = []
        self.secretary_card_id = ''
        for p in self.players:
            if p.index == self.napoleon_idx:
                continue
            for c in p.hand:
                if c.matches_type(suit, rank):
                    if not self.secretary_indices:
                        self.secretary_indices.append(p.index)
                        self.secretary_card_id = c.id
                    break

        for p in self.players:
            if p.index == self.napoleon_idx:
                continue
            if p.index in self.secretary_indices:
                p.role = Role.SECRETARY
            else:
                p.role = Role.UNITED_NATIONS

        self.phase = Phase.ANNOUNCE
        return True, 'announce'

    def confirm_announcement(self) -> tuple[bool, str]:
        """Human confirms they've seen the announcement. Starts play."""
        if self.phase != Phase.ANNOUNCE:
            return False, 'wrong_phase'
        # Snapshot hands after swap — the actual starting hands for play
        self.starting_hands = [[c.to_dict() for c in p.hand] for p in self.players]
        self.phase = Phase.PLAYING
        self.current_round = 1
        # Round 1: Napoleon leads
        self.lead_player_idx = self.napoleon_idx
        self.current_player_idx = self.napoleon_idx
        self.current_trick = []
        self.lead_suit = ''
        self.forced_jokers = {}
        return True, 'game_start'

    def get_valid_secretary_choices(self) -> list[dict]:
        """Return card types Napoleon can legally declare as secretary.
        Each choice includes 'self_secretary' flag if no other player holds it."""
        nap_hand = self.players[self.napoleon_idx].hand
        choices = []
        # Non-joker: need 2+ copies in hand
        seen = {}
        for c in nap_hand:
            if c.is_joker:
                continue
            key = (c.suit, c.rank)
            seen[key] = seen.get(key, 0) + 1
        for (suit, rank), count in seen.items():
            if count >= 2:
                # Check if any other player holds one
                others_hold = any(
                    any(c.matches_type(suit, rank) for c in p.hand)
                    for p in self.players if p.index != self.napoleon_idx
                )
                choices.append({
                    'suit': suit, 'rank': rank,
                    'self_secretary': not others_hold,
                })
        # Jokers: ALL 6 types are valid
        all_joker_ranks = ['big1', 'big2', 'mid1', 'mid2', 'small1', 'small2']
        for jr in all_joker_ranks:
            others_hold = any(
                any(c.matches_type('joker', jr) for c in p.hand)
                for p in self.players if p.index != self.napoleon_idx
            )
            choices.append({
                'suit': 'joker', 'rank': jr,
                'self_secretary': not others_hold,
            })
        return choices

    # ------------------------------------------------------------------
    # Helper: is this card the secretary card?
    # ------------------------------------------------------------------
    def _is_secretary_card(self, card: Card) -> bool:
        if self.secretary_card_id:
            return card.id == self.secretary_card_id
        return False

    # ------------------------------------------------------------------
    # Play phase
    # ------------------------------------------------------------------
    def get_playable_cards(self, player_idx: int) -> list[Card]:
        hand = self.players[player_idx].hand
        if not hand:
            return []

        # Forced joker overrides everything — UNLESS it's the secretary card
        if player_idx in self.forced_jokers:
            fc = self.forced_jokers[player_idx]
            if fc in hand and not self._is_secretary_card(fc):
                return [fc]
            # Secretary card joker: not forced, fall through to normal logic

        is_leading = len(self.current_trick) == 0

        if is_leading:
            if self.current_round == 1:
                # Round 1 lead only: no secretary, joker, or trump
                ok = [c for c in hand
                      if not c.is_joker
                      and not self._is_secretary_card(c)
                      and c.suit != self.trump_suit]
                return ok if ok else list(hand)
            return list(hand)

        # Following — normal rules (round 1 followers have no extra restrictions)
        always = [c for c in hand if c.is_joker or self._is_secretary_card(c)]

        follow = [c for c in hand
                  if not c.is_joker
                  and not self._is_secretary_card(c)
                  and c.suit == self.lead_suit]

        if follow:
            return follow + always

        # Void in lead suit — can play anything
        print(f'[DEBUG] P{player_idx} void in {self.lead_suit}, hand suits: {set(c.suit for c in hand if not c.is_joker)}')
        return list(hand)

    def play_card(self, player_idx: int, card_id: str) -> tuple[bool, str, dict | None]:
        if player_idx != self.current_player_idx:
            return False, 'not_your_turn', None
        player = self.players[player_idx]
        card = next((c for c in player.hand if c.id == card_id), None)
        if card is None:
            return False, 'card_not_found', None

        playable = self.get_playable_cards(player_idx)
        if card not in playable:
            return False, 'illegal_play', None

        player.hand.remove(card)
        self.current_trick.append((player_idx, card))

        if player_idx in self.forced_jokers:
            del self.forced_jokers[player_idx]

        is_leading = len(self.current_trick) == 1
        if is_leading:
            if card.is_joker or self._is_secretary_card(card):
                self.pending_suit_chooser = player_idx
                if player.is_ai:
                    self.lead_suit = self._ai_choose_lead_suit(player_idx)
                    jtype = self._check_call_joker(card)
                    if jtype:
                        self._ai_call_joker(player_idx, jtype)
                else:
                    self.phase = Phase.CHOOSE_LEAD_SUIT
                    return True, 'choose_lead_suit', None
            else:
                self.lead_suit = card.suit
                jtype = self._check_call_joker(card)
                if jtype:
                    if player.is_ai:
                        self._ai_call_joker(player_idx, jtype)
                    else:
                        self.pending_call_joker_type = jtype
                        self.phase = Phase.CHOOSE_CALL_JOKER
                        return True, 'choose_call_joker', None

        if len(self.current_trick) == 6:
            return self._resolve_trick()

        self.current_player_idx = (self.current_player_idx + 1) % 6
        return True, 'card_played', None

    def set_lead_suit(self, suit: str) -> tuple[bool, str]:
        if suit not in SUITS:
            return False, 'invalid_suit'
        self.lead_suit = suit
        self.phase = Phase.PLAYING
        if self.current_trick:
            _, lead_card = self.current_trick[0]
            jtype = self._check_call_joker(lead_card)
            if jtype:
                leader = self.players[self.lead_player_idx]
                if leader.is_ai:
                    self._ai_call_joker(self.lead_player_idx, jtype)
                else:
                    self.pending_call_joker_type = jtype
                    self.phase = Phase.CHOOSE_CALL_JOKER
                    return True, 'choose_call_joker'
        self.current_player_idx = (self.lead_player_idx + 1) % 6
        return True, 'suit_chosen'

    def _ai_choose_lead_suit(self, player_idx: int) -> str:
        hand = self.players[player_idx].hand
        suit_counts: dict[str, int] = {}
        for c in hand:
            if not c.is_joker:
                suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
        if suit_counts:
            return max(suit_counts, key=suit_counts.get)
        return self.trump_suit

    # ------------------------------------------------------------------
    # Call-joker mechanism (rounds 2-5)
    # ------------------------------------------------------------------
    def _check_call_joker(self, lead_card: Card):
        """Check if lead card triggers call-joker. Returns joker_type if choice needed."""
        if self.current_round < 2 or self.current_round > 5:
            return None
        if lead_card.is_joker or lead_card.suit != self.trump_suit:
            return None
        if lead_card.rank not in CALL_JOKER_MAP:
            return None
        return CALL_JOKER_MAP[lead_card.rank]  # 'big', 'mid', or 'small'

    def call_joker(self, joker_rank: str, set_next_player=True):
        """Force a specific joker to be played."""
        if joker_rank not in JOKER_PRIORITY:
            return False, 'invalid_joker'
        self._force_joker_rank(joker_rank)
        if not hasattr(self, 'called_joker_ranks'):
            self.called_joker_ranks = set()
        self.called_joker_ranks.add(joker_rank)
        self.phase = Phase.PLAYING
        if set_next_player:
            self.current_player_idx = (self.lead_player_idx + 1) % 6
        return True, 'joker_called'

    def get_uncalled_joker(self) -> str | None:
        """Return the other joker rank of same type if not yet called this round."""
        jtype = getattr(self, 'pending_call_joker_type', None)
        if not jtype:
            return None
        called = getattr(self, 'called_joker_ranks', set())
        rank1 = jtype + '1'
        rank2 = jtype + '2'
        if rank1 not in called:
            return rank1
        if rank2 not in called:
            return rank2
        return None

    def _ai_maybe_add_call(self, player_idx: int, uncalled_rank: str):
        """AI decides whether to add a call for the remaining joker."""
        # Only call if the uncalled joker is held by an enemy
        holder = -1
        for p in self.players:
            if p.index == self.lead_player_idx or p.index == player_idx:
                continue
            for c in p.hand:
                if c.is_joker and c.rank == uncalled_rank and not self._is_secretary_card(c):
                    holder = p.index
                    break
            if holder >= 0:
                break
        if holder < 0:
            return  # nobody holds it
        # Check if holder is enemy
        my_role = self.players[player_idx].role
        holder_role = self.players[holder].role
        ally_roles = set()
        if my_role in (Role.NAPOLEON, Role.SECRETARY):
            ally_roles = {Role.NAPOLEON, Role.SECRETARY}
        else:
            ally_roles = {Role.UNITED_NATIONS, Role.UNKNOWN}
        if holder_role not in ally_roles:
            # Enemy holds it — call it out
            self.call_joker(uncalled_rank, set_next_player=False)

    def _force_joker_rank(self, rank: str):
        """Force a single joker rank to be played by its holder."""
        for p in self.players:
            if p.index == self.lead_player_idx:
                continue
            for c in p.hand:
                if c.is_joker and c.rank == rank and not self._is_secretary_card(c):
                    self.forced_jokers[p.index] = c
                    return

    def _ai_call_joker(self, leader_idx: int, jtype: str):
        """AI chooses which joker to call. Prefers the one held by a non-ally."""
        rank1 = jtype + '1'
        rank2 = jtype + '2'

        def _held_by(rank):
            """Return player index holding this joker, or -1."""
            for p in self.players:
                if p.index == leader_idx:
                    continue
                for c in p.hand:
                    if c.is_joker and c.rank == rank:
                        return p.index
            return -1

        holder1 = _held_by(rank1)
        holder2 = _held_by(rank2)

        # Prefer calling one held by an opponent (not secretary/napoleon ally)
        leader_role = self.players[leader_idx].role
        ally_indices = set()
        if leader_role == Role.NAPOLEON:
            ally_indices = set(self.secretary_indices)
        elif leader_role == Role.SECRETARY:
            ally_indices = {self.napoleon_idx}

        # Pick the one held by a non-ally; if both or neither, pick whichever exists
        # set_next_player=False: caller (play_card) manages current_player_idx
        if holder1 >= 0 and holder1 not in ally_indices:
            self.call_joker(rank1, set_next_player=False)
        elif holder2 >= 0 and holder2 not in ally_indices:
            self.call_joker(rank2, set_next_player=False)
        elif holder1 >= 0:
            self.call_joker(rank1, set_next_player=False)
        elif holder2 >= 0:
            self.call_joker(rank2, set_next_player=False)
        else:
            # Neither joker exists — just resume play, caller manages player idx
            self.phase = Phase.PLAYING

    # ------------------------------------------------------------------
    # Trick resolution
    # ------------------------------------------------------------------
    def _card_priority(self, card: Card, play_order: int) -> tuple:
        tiebreak = 1000 - play_order
        if self._is_secretary_card(card):
            return (5, 0, tiebreak)
        if card.is_joker:
            if self.current_round == 25:
                return (0, 0, tiebreak)
            return (4, card.joker_priority, tiebreak)
        if card.suit == self.trump_suit:
            return (3, card.rank_value, tiebreak)
        if card.suit == self.lead_suit:
            return (2, card.rank_value, tiebreak)
        return (0, card.rank_value, tiebreak)

    def _resolve_trick(self) -> tuple[bool, str, dict]:
        best_idx = 0
        best_prio = self._card_priority(self.current_trick[0][1], 0)
        for i in range(1, 6):
            prio = self._card_priority(self.current_trick[i][1], i)
            if prio > best_prio:
                best_prio = prio
                best_idx = i

        # Check if secretary card was played this trick (reveals secretary)
        just_revealed = False
        if not self.secretary_revealed:
            for _, c in self.current_trick:
                if self._is_secretary_card(c):
                    self.secretary_revealed = True
                    just_revealed = True
                    break

        # Transfer secretary's accumulated points from UN to Napoleon on reveal
        if just_revealed:
            for p in self.players:
                if p.role == Role.SECRETARY and p.points_won > 0:
                    self.un_team_points -= p.points_won
                    self.napoleon_team_points += p.points_won

        winner_pidx = self.current_trick[best_idx][0]
        winner = self.players[winner_pidx]
        points = sum(1 for _, c in self.current_trick if c.is_point)

        # Secretary counts as UN until revealed
        if winner.role == Role.NAPOLEON:
            self.napoleon_team_points += points
        elif winner.role == Role.SECRETARY and self.secretary_revealed:
            self.napoleon_team_points += points
        else:
            self.un_team_points += points
        winner.points_won += points

        result = {
            'round': self.current_round,
            'winner': winner_pidx,
            'points': points,
            'cards': [(idx, c.to_dict()) for idx, c in self.current_trick],
            'napoleon_points': self.napoleon_team_points,
            'un_points': self.un_team_points,
        }
        self.last_trick_cards = list(self.current_trick)
        self.last_trick_winner = winner_pidx
        self.last_trick_points = points
        self.trick_history.append({
            'round': self.current_round,
            'cards': [(idx, c.to_dict()) for idx, c in self.current_trick],
            'winner': winner_pidx,
            'points': points,
            'lead_player': self.lead_player_idx,
            'lead_suit': self.lead_suit,
            'secretary_revealed': self.secretary_revealed,
        })

        if self.current_round >= 25:
            return self._end_game(result)

        # Don't clear trick yet — let server pause to show all 6 cards
        self._pending_next = {
            'next_round': self.current_round + 1,
            'next_leader': winner_pidx,
        }
        return True, 'trick_complete', result

    def advance_to_next_trick(self):
        """Clear the completed trick and set up next round. Called after pause."""
        self.called_joker_ranks = set()
        self.pending_call_joker_type = None
        pn = getattr(self, '_pending_next', None)
        if not pn:
            return
        self.current_round = pn['next_round']
        self.current_trick = []
        self.lead_suit = ''
        self.lead_player_idx = pn['next_leader']
        self.current_player_idx = pn['next_leader']
        self.forced_jokers = {}
        self._pending_next = None

    def _end_game(self, result: dict) -> tuple[bool, str, dict]:
        if self.napoleon_team_points >= self.contract_points:
            self.winner = 'napoleon'
        else:
            self.winner = 'united_nations'
        self.phase = Phase.FINISHED
        result['game_over'] = True
        result['winner'] = self.winner
        result['contract'] = self.contract_points
        result['napoleon_final'] = self.napoleon_team_points
        result['un_final'] = self.un_team_points
        result['secretary_indices'] = self.secretary_indices
        result['secretary_card'] = {
            'suit': self.secretary_card_suit,
            'rank': self.secretary_card_rank,
        }
        return True, 'game_over', result

    # ------------------------------------------------------------------
    # State serialisation
    # ------------------------------------------------------------------
    def get_state(self, player_idx: int) -> dict:
        p = self.players[player_idx]
        reveal = self.phase == Phase.FINISHED

        state = {
            'phase': self.phase.value,
            'players': [pl.to_dict(reveal_role=reveal,
                                   reveal_secretary=self.secretary_revealed)
                        for pl in self.players],
            'hand': [c.to_dict() for c in p.hand],
            'current_round': self.current_round,
            'trump_suit': self.trump_suit,
            'contract_points': self.contract_points,
            'napoleon_idx': self.napoleon_idx,
            'napoleon_points': self.napoleon_team_points,
            'un_points': self.un_team_points,
            'current_player_idx': self.current_player_idx,
            'lead_suit': self.lead_suit,
            'lead_player_idx': self.lead_player_idx,
            'current_trick': [(idx, c.to_dict()) for idx, c in self.current_trick],
            'bid_history': self.bid_history,
            'current_bidder_idx': self.current_bidder_idx,
            'highest_bid': self.highest_bid,
            'highest_bidder_idx': self.highest_bidder_idx,
            'winner': self.winner,
            'my_index': player_idx,
            'my_role': p.role.value,
            'pending_call_joker_type': getattr(self, 'pending_call_joker_type', None),
            'called_jokers': list(getattr(self, 'called_joker_ranks', set())),
            'uncalled_joker': self.get_uncalled_joker() if hasattr(self, 'pending_call_joker_type') else None,
            'trick_history': self.trick_history,
            'secretary_revealed': self.secretary_revealed,
            'last_trick': {
                'cards': [(idx, c.to_dict()) for idx, c in self.last_trick_cards],
                'winner': self.last_trick_winner,
                'points': self.last_trick_points,
            } if self.last_trick_cards else None,
        }

        if self.phase == Phase.PLAYING and self.current_player_idx == player_idx:
            state['playable_ids'] = [c.id for c in self.get_playable_cards(player_idx)]

        if self.phase == Phase.SWAP_CARDS and player_idx == self.napoleon_idx:
            state['bottom_cards'] = [c.to_dict() for c in self.bottom_cards]

        if self.phase == Phase.CHOOSE_SECRETARY and player_idx == self.napoleon_idx:
            state['valid_secretary_choices'] = self.get_valid_secretary_choices()

        if self.discarded_cards:
            state['discarded_points'] = [c.to_dict() for c in self.discarded_cards if c.is_point]

        # Secretary card type is public info once declared
        if self.secretary_card_suit:
            state['secretary_card'] = {
                'suit': self.secretary_card_suit,
                'rank': self.secretary_card_rank,
                'id': self.secretary_card_id,
            }
            # Napoleon's own copies: don't highlight if another player is secretary
            if player_idx == self.napoleon_idx:
                state['hide_secretary_highlight'] = len(self.secretary_indices) > 0

        if reveal:
            state['secretary_indices'] = self.secretary_indices
            state['replay'] = {
                'initial_hands': self.initial_hands,
                'initial_bottom': self.initial_bottom,
                'starting_hands': getattr(self, 'starting_hands', self.initial_hands),
                'tricks': self.trick_history,
                'discarded_cards': [c.to_dict() for c in self.discarded_cards],
                'bid_history': self.bid_history,
            }

        return state

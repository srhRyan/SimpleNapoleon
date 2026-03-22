import random

SUITS = ['spades', 'hearts', 'diamonds', 'clubs']
SUIT_SYMBOLS = {'spades': '♠', 'hearts': '♥', 'diamonds': '♦', 'clubs': '♣'}
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
RANK_ORDER = {r: i for i, r in enumerate(RANKS)}
POINT_RANKS = {'J', 'Q', 'K', 'A'}

JOKER_PRIORITY = {
    'big1': 6, 'big2': 5,
    'mid1': 4, 'mid2': 3,
    'small1': 2, 'small2': 1,
}
JOKER_DISPLAY = {
    'big1': '大鬼1', 'big2': '大鬼2',
    'mid1': '中鬼1', 'mid2': '中鬼2',
    'small1': '小鬼1', 'small2': '小鬼2',
}

# Trump rank -> joker type it calls out (rounds 2-5 only)
CALL_JOKER_MAP = {'3': 'big', '6': 'small', '9': 'mid'}


class Card:
    __slots__ = ('suit', 'rank', 'deck_index')

    def __init__(self, suit: str, rank: str, deck_index: int = 0):
        self.suit = suit
        self.rank = rank
        self.deck_index = deck_index

    @property
    def id(self) -> str:
        if self.is_joker:
            return f'joker_{self.rank}'
        return f'{self.suit}_{self.rank}_{self.deck_index}'

    @property
    def is_joker(self) -> bool:
        return self.suit == 'joker'

    @property
    def is_point(self) -> bool:
        return not self.is_joker and self.rank in POINT_RANKS

    @property
    def rank_value(self) -> int:
        return RANK_ORDER.get(self.rank, -1)

    @property
    def joker_type(self) -> str | None:
        if not self.is_joker:
            return None
        for prefix in ('big', 'mid', 'small'):
            if self.rank.startswith(prefix):
                return prefix
        return None

    @property
    def joker_priority(self) -> int:
        return JOKER_PRIORITY.get(self.rank, 0)

    @property
    def display(self) -> str:
        if self.is_joker:
            return JOKER_DISPLAY[self.rank]
        return f'{SUIT_SYMBOLS[self.suit]}{self.rank}'

    def matches_type(self, suit: str, rank: str) -> bool:
        return self.suit == suit and self.rank == rank

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'suit': self.suit,
            'rank': self.rank,
            'deck_index': self.deck_index,
            'is_joker': self.is_joker,
            'is_point': self.is_point,
            'display': self.display,
        }

    def __eq__(self, other):
        return isinstance(other, Card) and self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return self.display


def sort_key(card: Card) -> tuple:
    suit_order = {'spades': 0, 'hearts': 1, 'diamonds': 2, 'clubs': 3, 'joker': 4}
    return (suit_order.get(card.suit, 5), card.rank_value, card.deck_index)


def create_deck() -> list[Card]:
    """Create full 162-card deck: 3 standard decks + 6 jokers."""
    cards = []
    joker_map = {0: ('big1', 'big2'), 1: ('mid1', 'mid2'), 2: ('small1', 'small2')}
    for di in range(3):
        for suit in SUITS:
            for rank in RANKS:
                cards.append(Card(suit, rank, di))
        j1, j2 = joker_map[di]
        cards.append(Card('joker', j1, di))
        cards.append(Card('joker', j2, di))
    return cards


def shuffle_and_deal(cards: list[Card]) -> tuple[list[list[Card]], list[Card]]:
    """Shuffle and deal: 25 cards to each of 6 players, 12 to bottom."""
    deck = cards[:]
    random.shuffle(deck)
    hands = [sorted(deck[i * 25:(i + 1) * 25], key=sort_key) for i in range(6)]
    bottom = deck[150:162]
    return hands, bottom

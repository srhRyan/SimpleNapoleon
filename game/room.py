"""
Room system for multiplayer Napoleon.

Room lifecycle:
  1. Host creates room → 6-digit code
  2. Players join with code → fill slots
  3. Host can set slots to AI (strategy/proficiency)
  4. Host can remove players/AI to vacate slots
  5. All 6 ready → Host starts game
  6. Game plays, state sent per-player
  7. Game ends → back to lobby
"""

import random
import string
from .engine import GameEngine, Phase, Player
from .ai import AI


class Slot:
    def __init__(self, index: int):
        self.index = index
        self.type = 'empty'       # 'empty', 'human', 'ai'
        self.name = ''
        self.sid = ''             # socket ID for human
        self.ai_level = 3
        self.ai_strategy = 'conservative'
        self.ready = False

    def set_human(self, name: str, sid: str):
        self.type = 'human'
        self.name = name
        self.sid = sid
        self.ready = False

    def set_ai(self, level: int = 3, strategy: str = 'conservative'):
        self.type = 'ai'
        self.name = f'AI-{self.index}'
        self.sid = ''
        self.ai_level = level
        self.ai_strategy = strategy
        self.ready = True

    def vacate(self):
        self.type = 'empty'
        self.name = ''
        self.sid = ''
        self.ready = False

    def to_dict(self):
        return {
            'index': self.index,
            'type': self.type,
            'name': self.name,
            'ai_level': self.ai_level,
            'ai_strategy': self.ai_strategy,
            'ready': self.ready,
        }


class Room:
    def __init__(self, room_id: str, host_sid: str, host_name: str):
        self.room_id = room_id
        self.host_sid = host_sid
        self.state = 'waiting'    # 'waiting', 'playing', 'finished'
        self.slots = [Slot(i) for i in range(6)]
        self.slots[0].set_human(host_name, host_sid)
        self.slots[0].ready = True  # host is always ready
        self.engine = GameEngine()
        self.ai = AI(self.engine)
        self.saved_deal = None
        self.auto_play = {}       # sid -> bool, per-player autopilot
        self.skip_votes = set()   # sids that voted to skip
        self.public = False       # visible in public room list

    @property
    def all_ready(self) -> bool:
        return all(
            s.type != 'empty' and s.ready
            for s in self.slots
        )

    @property
    def all_filled(self) -> bool:
        return all(s.type != 'empty' for s in self.slots)

    @property
    def human_sids(self) -> list[str]:
        return [s.sid for s in self.slots if s.type == 'human' and s.sid]

    @property
    def human_count(self) -> int:
        return sum(1 for s in self.slots if s.type == 'human')

    @property
    def all_voted_skip(self) -> bool:
        hsids = set(self.human_sids)
        return hsids and self.skip_votes >= hsids

    def find_slot_by_sid(self, sid: str) -> Slot | None:
        for s in self.slots:
            if s.type == 'human' and s.sid == sid:
                return s
        return None

    def find_empty_slot(self) -> Slot | None:
        for s in self.slots:
            if s.type == 'empty':
                return s
        return None

    def player_index_for_sid(self, sid: str) -> int:
        for s in self.slots:
            if s.type == 'human' and s.sid == sid:
                return s.index
        return -1

    def is_ai_player(self, player_idx: int) -> bool:
        return self.slots[player_idx].type == 'ai'

    def start_game(self):
        """Initialize game engine from slot configuration."""
        ai_levels = [s.ai_level for s in self.slots]
        ai_strategies = [s.ai_strategy for s in self.slots]
        names = []
        for s in self.slots:
            if s.type == 'human':
                names.append(s.name)
            else:
                names.append(s.name or f'AI-{s.index}')

        self.engine.reset()
        # Setup players with correct names and AI config
        from .card import sort_key
        self.engine.players = []
        for i, s in enumerate(self.slots):
            is_ai = s.type == 'ai'
            p = Player(i, names[i], is_ai=is_ai,
                       ai_level=ai_levels[i], ai_strategy=ai_strategies[i])
            self.engine.players.append(p)

        if self.saved_deal:
            from .card import Card
            hands = []
            for h in self.saved_deal['hands']:
                hands.append([Card(c['suit'], c['rank'], c.get('deck_index', 0)) for c in h])
            bottom = [Card(c['suit'], c['rank'], c.get('deck_index', 0)) for c in self.saved_deal['bottom']]
            self.engine.start_game(saved_deal={'hands': hands, 'bottom': bottom})
        else:
            self.engine.start_game()

        self.ai = AI(self.engine)
        self.state = 'playing'

    def to_dict(self):
        return {
            'room_id': self.room_id,
            'state': self.state,
            'slots': [s.to_dict() for s in self.slots],
            'host_sid': self.host_sid,
            'all_ready': self.all_ready,
            'all_filled': self.all_filled,
            'public': self.public,
        }

    def to_list_dict(self):
        """Brief info for public room listing."""
        host_name = self.slots[0].name
        humans = sum(1 for s in self.slots if s.type == 'human')
        ais = sum(1 for s in self.slots if s.type == 'ai')
        empty = sum(1 for s in self.slots if s.type == 'empty')
        return {
            'room_id': self.room_id,
            'host': host_name,
            'humans': humans,
            'ais': ais,
            'empty': empty,
            'state': self.state,
        }


class RoomManager:
    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self.sid_to_room: dict[str, str] = {}  # socket ID -> room_id

    def create_room(self, host_sid: str, host_name: str) -> Room:
        room_id = self._generate_id()
        room = Room(room_id, host_sid, host_name)
        self.rooms[room_id] = room
        self.sid_to_room[host_sid] = room_id
        return room

    def join_room(self, room_id: str, sid: str, name: str) -> tuple[bool, str]:
        room = self.rooms.get(room_id)
        if not room:
            return False, 'Room not found'
        if room.state != 'waiting':
            return False, 'Game already in progress'
        slot = room.find_empty_slot()
        if not slot:
            return False, 'Room is full'
        slot.set_human(name, sid)
        self.sid_to_room[sid] = room_id
        return True, 'joined'

    def leave_room(self, sid: str):
        room_id = self.sid_to_room.pop(sid, None)
        if not room_id:
            return
        room = self.rooms.get(room_id)
        if not room:
            return
        slot = room.find_slot_by_sid(sid)
        if slot:
            slot.vacate()
        # If host left, destroy room
        if sid == room.host_sid:
            for s in room.slots:
                if s.type == 'human' and s.sid:
                    self.sid_to_room.pop(s.sid, None)
            del self.rooms[room_id]

    def get_room_for_sid(self, sid: str) -> Room | None:
        room_id = self.sid_to_room.get(sid)
        return self.rooms.get(room_id) if room_id else None

    def list_public_rooms(self, page=0, per_page=6) -> dict:
        public = [r for r in self.rooms.values()
                  if r.public and r.state == 'waiting']
        total = len(public)
        start = page * per_page
        items = [r.to_list_dict() for r in public[start:start + per_page]]
        return {'rooms': items, 'page': page, 'total': total, 'pages': (total + per_page - 1) // per_page}

    def _generate_id(self) -> str:
        while True:
            code = ''.join(random.choices(string.digits, k=6))
            if code not in self.rooms:
                return code

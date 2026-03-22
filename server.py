"""
Napoleon card game server — Flask + Socket.IO.
Supports single-player and multiplayer via rooms.
Run locally: python server.py
Deploy: use wsgi.py for PythonAnywhere
"""

import os
import time
import threading
from flask import Flask, render_template, request as flask_request
from flask_socketio import SocketIO, emit, join_room, leave_room

from game.engine import GameEngine, Phase
from game.ai import AI
from game.room import Room, RoomManager
from game.logger import dump_game_log

import mimetypes
mimetypes.init()
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'napoleon-secret')

async_mode = 'threading'

socketio = SocketIO(app, async_mode=async_mode, cors_allowed_origins='*')

# Use socketio.sleep for cooperative async
def _sleep(seconds):
    socketio.sleep(seconds)

room_mgr = RoomManager()

# Per-room flags
room_locks = {}      # room_id -> ai_running flag
room_skip = {}       # room_id -> skip_requested flag
_game_logged = {}    # room_id -> bool


@app.route('/')
def index():
    return render_template('index.html')


@app.after_request
def fix_mime_types(response):
    if flask_request.path.endswith('.js') and 'javascript' not in response.content_type:
        response.content_type = 'application/javascript'
    elif flask_request.path.endswith('.css') and 'css' not in response.content_type:
        response.content_type = 'text/css'
    return response


# ==================================================================
# Helpers
# ==================================================================
def get_room(sid=None) -> Room | None:
    return room_mgr.get_room_for_sid(sid or '')


def send_room_state(room: Room):
    """Send room lobby state to all humans in room."""
    data = room.to_dict()
    for sid in room.human_sids:
        socketio.emit('room_state', data, to=sid)


def broadcast_game_state(room: Room):
    """Send game state to each human player (personalized view)."""
    rid = room.room_id
    if room.engine.phase == Phase.FINISHED and not _game_logged.get(rid):
        _game_logged[rid] = True
        try:
            state = room.engine.get_state(0)
            path = dump_game_log(state)
            if path:
                print(f'[LOG] Game log: {path}_*.txt')
        except Exception as e:
            print(f'[LOG] Error: {e}')

    for s in room.slots:
        if s.type == 'human' and s.sid:
            state = room.engine.get_state(s.index)
            socketio.emit('game_state', state, to=s.sid)


def is_ai_turn(room: Room) -> bool:
    """Check if current player is AI."""
    if room.engine.phase != Phase.PLAYING:
        return False
    idx = room.engine.current_player_idx
    return room.is_ai_player(idx)


def is_human_auto(room: Room, player_idx: int) -> bool:
    """Check if a human player has autopilot on."""
    s = room.slots[player_idx]
    if s.type != 'human':
        return False
    return room.auto_play.get(s.sid, False)


def should_ai_act(room: Room) -> bool:
    """Should AI drive the next action? True if current player is AI or human with autopilot."""
    e = room.engine
    if e.phase == Phase.CHOOSE_CALL_JOKER:
        leader = e.lead_player_idx
        return room.is_ai_player(leader) or is_human_auto(room, leader)
    if e.phase == Phase.ANNOUNCE:
        return False  # always wait for human confirm
    if e.phase not in (Phase.PLAYING, Phase.BIDDING, Phase.CHOOSE_TRUMP,
                       Phase.SWAP_CARDS, Phase.CHOOSE_SECRETARY):
        return False
    if e.phase == Phase.BIDDING:
        idx = e.current_bidder_idx
    elif e.phase in (Phase.CHOOSE_TRUMP, Phase.SWAP_CARDS, Phase.CHOOSE_SECRETARY):
        idx = e.napoleon_idx
    else:
        idx = e.current_player_idx
    return room.is_ai_player(idx) or is_human_auto(room, idx)


# ==================================================================
# AI driver (per room)
# ==================================================================
def run_ai_for_room(room_id: str):
    """Background task: drive AI actions for a room."""
    if room_locks.get(room_id):
        return
    room_locks[room_id] = True
    try:
        room = room_mgr.rooms.get(room_id)
        if not room:
            return
        _drive_room_ai(room)
    finally:
        room_locks[room_id] = False


def _drive_room_ai(room: Room):
    e = room.engine
    ai = room.ai
    rid = room.room_id

    # --- Bidding ---
    redeals = 0
    while e.phase == Phase.BIDDING:
        if not should_ai_act(room):
            broadcast_game_state(room)
            return
        _sleep(0.6)
        if room_skip.get(rid):
            return
        idx = e.current_bidder_idx
        bid = ai.decide_bid(idx)
        ok, result = e.place_bid(idx, bid)
        if not ok:
            continue
        broadcast_game_state(room)
        if result == 'bidding_complete':
            break
        if result == 'all_passed':
            redeals += 1
            if redeals >= 5:
                e.place_bid(e.current_bidder_idx, 23)
                broadcast_game_state(room)
                break
            e.start_game()
            broadcast_game_state(room)
            continue

    # --- Pre-play ---
    for phase_check in (Phase.CHOOSE_TRUMP, Phase.SWAP_CARDS, Phase.CHOOSE_SECRETARY):
        if e.phase == phase_check:
            if not should_ai_act(room):
                broadcast_game_state(room)
                return
            _sleep(0.6)
            if room_skip.get(rid):
                return
            if phase_check == Phase.CHOOSE_TRUMP:
                e.choose_trump(ai.decide_trump(e.napoleon_idx))
            elif phase_check == Phase.SWAP_CARDS:
                e.swap_cards(ai.decide_discard(e.napoleon_idx))
            elif phase_check == Phase.CHOOSE_SECRETARY:
                s, r = ai.decide_secretary(e.napoleon_idx)
                e.choose_secretary(s, r)
            broadcast_game_state(room)

    # --- Announcement ---
    if e.phase == Phase.ANNOUNCE:
        broadcast_game_state(room)
        return  # always wait for human confirm

    # --- Playing ---
    fail_count = 0
    while e.phase in (Phase.PLAYING, Phase.CHOOSE_CALL_JOKER):
        if e.phase == Phase.CHOOSE_CALL_JOKER:
            if not should_ai_act(room):
                broadcast_game_state(room)
                return
            jtype = getattr(e, 'pending_call_joker_type', 'big')
            e._ai_call_joker(e.lead_player_idx, jtype)
            e.current_player_idx = (e.lead_player_idx + 1) % 6
            broadcast_game_state(room)
            continue
        if room_skip.get(rid):
            return
        if not should_ai_act(room):
            broadcast_game_state(room)
            return
        _sleep(0.6)
        if room_skip.get(rid):
            return
        idx = e.current_player_idx
        card_id = ai.decide_play(idx)
        if not card_id:
            break
        ok, result, trick_result = e.play_card(idx, card_id)
        if not ok:
            fail_count += 1
            if fail_count > 10:
                playable = e.get_playable_cards(idx)
                if playable:
                    e.play_card(idx, playable[0].id)
                fail_count = 0
            continue
        fail_count = 0
        if result == 'choose_lead_suit':
            e.set_lead_suit(ai.decide_lead_suit(idx))
        if result == 'choose_call_joker':
            jtype = getattr(e, 'pending_call_joker_type', 'big')
            e._ai_call_joker(e.lead_player_idx, jtype)
            e.current_player_idx = (e.current_player_idx + 1) % 6
        broadcast_game_state(room)
        if trick_result:
            _sleep(1.2)
            if room_skip.get(rid) or trick_result.get('game_over'):
                return
            e.advance_to_next_trick()
            broadcast_game_state(room)

    broadcast_game_state(room)


def start_ai_driver(room: Room):
    socketio.start_background_task(run_ai_for_room, room.room_id)


# ==================================================================
# Socket.IO: Connection
# ==================================================================
@socketio.on('connect')
def on_connect():
    emit('connected', {'msg': 'Welcome to Napoleon!'})


@socketio.on('disconnect')
def on_disconnect():
    from flask import request
    sid = request.sid
    room = get_room(sid)
    if not room:
        return
    rid = room.room_id
    if sid == room.host_sid:
        # Host disconnected — close room, notify all players
        for s in room.slots:
            if s.type == 'human' and s.sid and s.sid != sid:
                socketio.emit('room_closed', {'msg': 'Host disconnected — room closed'}, to=s.sid)
                room_mgr.sid_to_room.pop(s.sid, None)
        was_public = room.public
        room_mgr.sid_to_room.pop(sid, None)
        if rid in room_mgr.rooms:
            del room_mgr.rooms[rid]
        if was_public:
            broadcast_public_rooms()
    else:
        # Player disconnected — release their slot
        slot = room.find_slot_by_sid(sid)
        if slot:
            slot.vacate()
        room_mgr.sid_to_room.pop(sid, None)
        # If game is in progress, replace with AI
        if room.state == 'playing' and slot:
            slot.set_ai(level=3, strategy='conservative')
            room.engine.players[slot.index].is_ai = True
            room.engine.players[slot.index].name = f'AI-{slot.index}'
            start_ai_driver(room)
        send_room_state(room)


# ==================================================================
# Socket.IO: Room management
# ==================================================================
@socketio.on('create_room')
def on_create_room(data=None):
    name = data.get('name', 'Host') if data else 'Host'
    sid = data.get('sid', '') if data else ''
    # Use request.sid from flask-socketio
    from flask import request
    sid = request.sid
    room = room_mgr.create_room(sid, name)
    join_room(room.room_id)
    emit('room_created', {'room_id': room.room_id})
    send_room_state(room)


@socketio.on('join_room_req')
def on_join_room(data=None):
    if not data:
        return
    room_id = data.get('room_id', '')
    name = data.get('name', 'Player')
    from flask import request
    sid = request.sid
    ok, msg = room_mgr.join_room(room_id, sid, name)
    if not ok:
        emit('join_error', {'msg': msg})
        return
    join_room(room_id)
    emit('room_joined', {'room_id': room_id})
    room = room_mgr.rooms.get(room_id)
    if room:
        send_room_state(room)
        if room.public:
            broadcast_public_rooms()


@socketio.on('leave_room_req')
def on_leave_room(data=None):
    from flask import request
    sid = request.sid
    room = get_room(sid)
    if room:
        rid = room.room_id
        leave_room(rid)
        room_mgr.leave_room(sid)
        if rid in room_mgr.rooms:
            send_room_state(room_mgr.rooms[rid])


@socketio.on('set_room_public')
def on_set_room_public(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room or request.sid != room.host_sid:
        return
    room.public = data.get('public', False) if data else False
    send_room_state(room)
    broadcast_public_rooms()


def broadcast_public_rooms():
    """Notify all clients on the join screen that the public room list changed."""
    result = room_mgr.list_public_rooms(page=0)
    socketio.emit('public_rooms', result)


@socketio.on('list_public_rooms')
def on_list_public_rooms(data=None):
    page = data.get('page', 0) if data else 0
    result = room_mgr.list_public_rooms(page=page)
    emit('public_rooms', result)


@socketio.on('set_slot_ai')
def on_set_slot_ai(data=None):
    if not data:
        return
    from flask import request
    room = get_room(request.sid)
    if not room or request.sid != room.host_sid:
        return
    idx = data.get('index', -1)
    if idx < 0 or idx >= 6:
        return
    if idx == 0:
        return  # can't change host slot
    room.slots[idx].set_ai(
        level=data.get('level', 3),
        strategy=data.get('strategy', 'conservative'),
    )
    send_room_state(room)


@socketio.on('vacate_slot')
def on_vacate_slot(data=None):
    if not data:
        return
    from flask import request
    room = get_room(request.sid)
    if not room or request.sid != room.host_sid:
        return
    idx = data.get('index', -1)
    if idx < 0 or idx >= 6 or idx == 0:
        return
    old_sid = room.slots[idx].sid
    was_human = room.slots[idx].type == 'human'
    room.slots[idx].vacate()
    if old_sid:
        room_mgr.sid_to_room.pop(old_sid, None)
        if was_human:
            socketio.emit('room_closed', {'msg': 'You have been removed from the room'}, to=old_sid)
    send_room_state(room)
    if room.public:
        broadcast_public_rooms()


@socketio.on('player_ready')
def on_player_ready(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room:
        return
    slot = room.find_slot_by_sid(request.sid)
    if slot:
        slot.ready = True
    send_room_state(room)


@socketio.on('host_start')
def on_host_start(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room or request.sid != room.host_sid:
        return
    if not room.all_ready:
        emit('error', {'msg': 'Not all players ready'})
        return
    _game_logged[room.room_id] = False
    room.auto_play = {}  # reset all autopilot
    room.skip_votes = set()  # reset skip votes
    room.start_game()
    # Notify all humans autopilot is off
    for sid in room.human_sids:
        socketio.emit('auto_play_state', {'auto_play': False}, to=sid)
    broadcast_game_state(room)
    if room.public:
        broadcast_public_rooms()
    start_ai_driver(room)


@socketio.on('host_import_deal')
def on_host_import_deal(data=None):
    if not data:
        return
    from flask import request
    room = get_room(request.sid)
    if not room or request.sid != room.host_sid:
        return
    from game.card import Card, create_deck
    try:
        hands_raw = data.get('initial_hands', [])
        bottom_raw = data.get('bottom_cards', [])
        if len(hands_raw) != 6 or len(bottom_raw) != 12:
            emit('error', {'msg': 'Invalid deal format'})
            return
        # Validate
        all_cards = []
        for h in hands_raw:
            all_cards.extend(h)
        all_cards.extend(bottom_raw)
        imported_ids = sorted(Card(c['suit'], c['rank'], c.get('deck_index', 0)).id for c in all_cards)
        valid_ids = sorted(c.id for c in create_deck())
        if imported_ids != valid_ids:
            emit('error', {'msg': 'Invalid deal: cards don\'t match valid deck'})
            return
        room.saved_deal = {'hands': hands_raw, 'bottom': bottom_raw}
        emit('deal_imported', {'msg': 'Deal loaded successfully'})
    except Exception as ex:
        emit('error', {'msg': f'Invalid deal: {ex}'})


# ==================================================================
# Socket.IO: Single-player shortcut (backward compat)
# ==================================================================
@socketio.on('start_game')
def on_start_game(data=None):
    """Single mode: create room, fill with AI, start immediately."""
    from flask import request
    sid = request.sid
    name = data.get('name', 'Player') if data else 'Player'
    ai_levels = data.get('ai_levels', [3, 3, 3, 3, 3]) if data else [3] * 5
    ai_strategies = data.get('ai_strategies', ['conservative'] * 5) if data else ['conservative'] * 5

    # Clean up old room
    old_room = get_room(sid)
    if old_room:
        room_mgr.leave_room(sid)

    room = room_mgr.create_room(sid, name)
    room.slots[0].ai_level = ai_levels[0] if ai_levels else 3
    room.slots[0].ai_strategy = ai_strategies[0] if ai_strategies else 'conservative'
    for i in range(1, 6):
        lvl = ai_levels[i] if i < len(ai_levels) else ai_levels[-1] if ai_levels else 3
        strat = ai_strategies[i] if i < len(ai_strategies) else ai_strategies[-1] if ai_strategies else 'conservative'
        room.slots[i].set_ai(level=lvl, strategy=strat)
    join_room(room.room_id)

    _game_logged[room.room_id] = False
    room.auto_play = {}
    room.start_game()
    emit('auto_play_state', {'auto_play': False})
    broadcast_game_state(room)
    start_ai_driver(room)


# ==================================================================
# Socket.IO: Game actions (room-aware)
# ==================================================================
@socketio.on('bid')
def on_bid(data=None):
    from flask import request
    room = get_room(request.sid)
    print(f'[BID] sid={request.sid} room={room is not None} data={data}')
    if not room or room.engine.phase != Phase.BIDDING:
        print(f'[BID] rejected: no room or wrong phase')
        return
    pidx = room.player_index_for_sid(request.sid)
    print(f'[BID] pidx={pidx} current_bidder={room.engine.current_bidder_idx}')
    if pidx < 0 or room.engine.current_bidder_idx != pidx:
        emit('error', {'msg': 'not_your_turn'})
        return
    bid = data.get('bid', 0) if data else 0
    ok, result = room.engine.place_bid(pidx, bid)
    if not ok:
        emit('error', {'msg': result})
        return
    broadcast_game_state(room)
    if result == 'all_passed':
        room.engine.start_game()
        broadcast_game_state(room)
    start_ai_driver(room)


@socketio.on('choose_trump')
def on_choose_trump(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room or room.engine.phase != Phase.CHOOSE_TRUMP:
        return
    pidx = room.player_index_for_sid(request.sid)
    if pidx != room.engine.napoleon_idx:
        return
    ok, result = room.engine.choose_trump(data.get('suit', '') if data else '')
    if not ok:
        emit('error', {'msg': result})
        return
    broadcast_game_state(room)


@socketio.on('change_trump')
def on_change_trump(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room:
        return
    pidx = room.player_index_for_sid(request.sid)
    if pidx != room.engine.napoleon_idx:
        return
    ok, result = room.engine.change_trump(data.get('suit', '') if data else '')
    if not ok:
        emit('error', {'msg': result})
        return
    broadcast_game_state(room)


@socketio.on('swap_cards')
def on_swap_cards(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room or room.engine.phase != Phase.SWAP_CARDS:
        return
    pidx = room.player_index_for_sid(request.sid)
    if pidx != room.engine.napoleon_idx:
        return
    ok, result = room.engine.swap_cards(data.get('discard_ids', []) if data else [])
    if not ok:
        emit('error', {'msg': result})
        return
    broadcast_game_state(room)


@socketio.on('choose_secretary')
def on_choose_secretary(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room or room.engine.phase != Phase.CHOOSE_SECRETARY:
        return
    pidx = room.player_index_for_sid(request.sid)
    if pidx != room.engine.napoleon_idx:
        return
    ok, result = room.engine.choose_secretary(
        data.get('suit', '') if data else '',
        data.get('rank', '') if data else '',
    )
    if not ok:
        emit('error', {'msg': result})
        return
    broadcast_game_state(room)


@socketio.on('confirm_announcement')
def on_confirm_announcement(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room or room.engine.phase != Phase.ANNOUNCE:
        return
    room.engine.confirm_announcement()
    broadcast_game_state(room)
    if room.engine.phase == Phase.PLAYING:
        start_ai_driver(room)


@socketio.on('play_card')
def on_play_card(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room:
        return
    e = room.engine
    if e.phase not in (Phase.PLAYING, Phase.CHOOSE_LEAD_SUIT, Phase.CHOOSE_CALL_JOKER):
        return
    pidx = room.player_index_for_sid(request.sid)
    if pidx < 0 or e.current_player_idx != pidx:
        return
    ok, result, trick_result = e.play_card(pidx, data.get('card_id', '') if data else '')
    if not ok:
        emit('error', {'msg': result})
        return
    broadcast_game_state(room)
    if result in ('choose_lead_suit', 'choose_call_joker'):
        return
    if trick_result:
        def pause_then_continue():
            _sleep(1.2)
            if not trick_result.get('game_over'):
                e.advance_to_next_trick()
                broadcast_game_state(room)
                run_ai_for_room(room.room_id)
        socketio.start_background_task(pause_then_continue)
    else:
        start_ai_driver(room)


@socketio.on('choose_lead_suit')
def on_choose_lead_suit(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room or room.engine.phase != Phase.CHOOSE_LEAD_SUIT:
        return
    ok, result = room.engine.set_lead_suit(data.get('suit', '') if data else '')
    if not ok:
        emit('error', {'msg': result})
        return
    broadcast_game_state(room)
    if room.engine.phase == Phase.PLAYING:
        start_ai_driver(room)


@socketio.on('choose_call_joker')
def on_choose_call_joker(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room or room.engine.phase != Phase.CHOOSE_CALL_JOKER:
        return
    joker_rank = data.get('joker_rank', '') if data else ''
    ok, result = room.engine.call_joker(joker_rank)
    if not ok:
        emit('error', {'msg': result})
        return
    broadcast_game_state(room)
    if room.engine.phase == Phase.PLAYING:
        start_ai_driver(room)


@socketio.on('add_call_joker')
def on_add_call_joker(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room or room.engine.phase != Phase.PLAYING:
        return
    pidx = room.player_index_for_sid(request.sid)
    if pidx < 0 or room.engine.current_player_idx != pidx:
        return
    joker_rank = data.get('joker_rank', '') if data else ''
    room.engine.call_joker(joker_rank, set_next_player=False)
    broadcast_game_state(room)


@socketio.on('toggle_auto_play')
def on_toggle_auto(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room:
        return
    sid = request.sid
    room.auto_play[sid] = not room.auto_play.get(sid, False)
    emit('auto_play_state', {'auto_play': room.auto_play[sid]})
    if room.auto_play[sid] and room.state == 'playing':
        start_ai_driver(room)


@socketio.on('skip_to_end')
def on_skip_to_end(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room:
        return

    # Multi-human: requires vote from all humans
    if room.human_count > 1:
        room.skip_votes.add(request.sid)
        voted = len(room.skip_votes)
        total = room.human_count
        # Notify all humans of vote status
        for sid in room.human_sids:
            socketio.emit('skip_vote_status', {
                'voted': voted, 'total': total,
                'approved': room.all_voted_skip,
            }, to=sid)
        if not room.all_voted_skip:
            return  # wait for more votes
        room.skip_votes = set()  # reset for next time

    rid = room.room_id
    e = room.engine
    ai = room.ai

    # Wait for current AI driver to stop
    if room_locks.get(rid):
        room_skip[rid] = True
        for _ in range(50):
            _sleep(0.1)
            if not room_locks.get(rid):
                break
        room_skip[rid] = False

    room_locks[rid] = True
    try:
        if hasattr(e, '_pending_next') and e._pending_next:
            e.advance_to_next_trick()

        redeals = 0
        while e.phase == Phase.BIDDING:
            idx = e.current_bidder_idx
            ok, result = e.place_bid(idx, ai.decide_bid(idx))
            if result == 'bidding_complete':
                break
            if result == 'all_passed':
                redeals += 1
                if redeals >= 5:
                    e.place_bid(e.current_bidder_idx, 23)
                    break
                e.start_game()

        if e.phase == Phase.CHOOSE_TRUMP:
            e.choose_trump(ai.decide_trump(e.napoleon_idx))
        if e.phase == Phase.SWAP_CARDS:
            e.swap_cards(ai.decide_discard(e.napoleon_idx))
        if e.phase == Phase.CHOOSE_SECRETARY:
            s, r = ai.decide_secretary(e.napoleon_idx)
            e.choose_secretary(s, r)
        if e.phase == Phase.ANNOUNCE:
            e.confirm_announcement()

        safety = 0
        while e.phase in (Phase.PLAYING, Phase.CHOOSE_CALL_JOKER) and safety < 300:
            safety += 1
            if e.phase == Phase.CHOOSE_CALL_JOKER:
                jtype = getattr(e, 'pending_call_joker_type', 'big')
                e._ai_call_joker(e.lead_player_idx, jtype)
                e.current_player_idx = (e.lead_player_idx + 1) % 6
                continue
            idx = e.current_player_idx
            card_id = ai.decide_play(idx)
            if not card_id:
                break
            ok, result, trick_result = e.play_card(idx, card_id)
            if not ok:
                playable = e.get_playable_cards(idx)
                if playable:
                    e.play_card(idx, playable[0].id)
                else:
                    break
                continue
            if result == 'choose_lead_suit':
                e.set_lead_suit(ai.decide_lead_suit(idx))
            if result == 'choose_call_joker':
                jtype = getattr(e, 'pending_call_joker_type', 'big')
                e._ai_call_joker(e.lead_player_idx, jtype)
                e.current_player_idx = (e.current_player_idx + 1) % 6
            if trick_result:
                if trick_result.get('game_over'):
                    break
                e.advance_to_next_trick()

        broadcast_game_state(room)
    finally:
        room_locks[rid] = False


@socketio.on('save_deal')
def on_save_deal(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room:
        return
    deal = {
        'initial_hands': room.engine.initial_hands,
        'bottom_cards': room.engine.initial_bottom,
    }
    emit('deal_data', deal)


@socketio.on('replay_same')
def on_replay_same(data=None):
    from flask import request
    room = get_room(request.sid)
    if not room:
        return
    saved = getattr(room.engine, '_saved_deal', None)
    if not saved:
        emit('error', {'msg': 'No game to replay'})
        return
    room.saved_deal = {
        'hands': [[c.to_dict() for c in h] for h in saved['hands']],
        'bottom': [c.to_dict() for c in saved['bottom']],
    }
    _game_logged[room.room_id] = False
    room.auto_play = {}
    room.skip_votes = set()
    room.start_game()
    for sid in room.human_sids:
        socketio.emit('auto_play_state', {'auto_play': False}, to=sid)
    broadcast_game_state(room)
    start_ai_driver(room)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    debug = os.environ.get('DEBUG', 'true').lower() == 'true'
    socketio.run(app, host='0.0.0.0', port=port, debug=debug, allow_unsafe_werkzeug=True)

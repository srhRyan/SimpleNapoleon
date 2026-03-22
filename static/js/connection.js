/**
 * Socket.IO connection manager.
 */
const Connection = (() => {
  let socket = null;
  const handlers = {};

  function connect() {
    const isLocal = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
    socket = io({ transports: isLocal ? ['websocket', 'polling'] : ['polling'] });
    socket.on('connect', () => { console.log('[WS] Connected:', socket.id); _fire('connected'); });
    socket.on('disconnect', () => { console.log('[WS] Disconnected'); _fire('disconnected'); });
    socket.on('game_state', data => _fire('game_state', data));
    socket.on('error', data => _fire('error', data));
    socket.on('connected', data => _fire('welcome', data));
    socket.on('auto_play_state', data => _fire('auto_play_state', data));
    socket.on('deal_data', data => _fire('deal_data', data));
    // Room events
    socket.on('room_created', data => _fire('room_created', data));
    socket.on('room_joined', data => _fire('room_joined', data));
    socket.on('room_state', data => _fire('room_state', data));
    socket.on('join_error', data => _fire('join_error', data));
    socket.on('deal_imported', data => _fire('deal_imported', data));
    socket.on('skip_vote_status', data => _fire('skip_vote_status', data));
    socket.on('room_closed', data => _fire('room_closed', data));
    socket.on('public_rooms', data => _fire('public_rooms', data));
    socket.on('player_disconnected', data => _fire('player_disconnected', data));
    socket.on('player_replaced', data => _fire('player_replaced', data));
    socket.on('player_reconnected', data => _fire('player_reconnected', data));
    socket.on('rejoin_success', data => _fire('rejoin_success', data));
  }

  function emit(event, data) { if (socket) socket.emit(event, data); }
  function on(event, fn) { if (!handlers[event]) handlers[event] = []; handlers[event].push(fn); }
  function _fire(event, data) { (handlers[event] || []).forEach(fn => fn(data)); }

  return { connect, emit, on };
})();

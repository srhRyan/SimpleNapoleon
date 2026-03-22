/**
 * Main game controller — Single, Host, Join modes.
 */
(function () {
  let currentState = null;
  let prevPhase = null;
  let autoPlay = false;
  let importedDeal = null;
  let currentMode = null;   // 'single', 'host', 'join'
  let isHost = false;
  let currentRoomId = null;

  // ================================================================
  // Startup
  // ================================================================
  document.addEventListener('DOMContentLoaded', () => {
    Connection.connect();
    bindStartScreen();
    bindConnectionEvents();
    bindGameButtons();
  });

  function bindGameButtons() {
    document.getElementById('btn-auto-play').addEventListener('click', () => {
      Connection.emit('toggle_auto_play');
    });
    document.getElementById('btn-skip').addEventListener('click', () => {
      Connection.emit('skip_to_end');
    });
  }

  function bindStartScreen() {
    const singleOpts = document.getElementById('single-options');

    // Mode buttons
    document.getElementById('btn-single').addEventListener('click', () => {
      singleOpts.style.display = '';
    });
    document.getElementById('btn-host').addEventListener('click', () => {
      singleOpts.style.display = 'none';
      const name = document.getElementById('player-name').value.trim() || 'Host';
      Connection.emit('create_room', { name });
    });
    document.getElementById('btn-join').addEventListener('click', () => {
      singleOpts.style.display = 'none';
      Renderer.showScreen('join-screen');
      Connection.emit('list_public_rooms', { page: 0 });
    });

    // Single mode start
    document.getElementById('btn-start').addEventListener('click', () => {
      const name = document.getElementById('player-name').value.trim() || 'Player';
      const level = parseInt(document.getElementById('ai-level').value, 10);
      const strategy = document.getElementById('ai-strategy').value;
      currentMode = 'single';
      Connection.emit('start_game', {
        name,
        ai_levels: [level, level, level, level, level],
        ai_strategies: [strategy, strategy, strategy, strategy, strategy],
      });
      Renderer.showScreen('game-screen');
    });

    // Import deal
    const importInput = document.getElementById('import-deal');
    const importBtn = document.getElementById('btn-import');
    importInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) { importedDeal = null; importBtn.disabled = true; return; }
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          importedDeal = JSON.parse(ev.target.result);
          importBtn.disabled = !(importedDeal.initial_hands && importedDeal.bottom_cards);
        } catch { importedDeal = null; importBtn.disabled = true; }
      };
      reader.readAsText(file);
    });
    importBtn.addEventListener('click', () => {
      if (!importedDeal) return;
      const name = document.getElementById('player-name').value.trim() || 'Player';
      const level = parseInt(document.getElementById('ai-level').value, 10);
      const strategy = document.getElementById('ai-strategy').value;
      currentMode = 'single';
      Connection.emit('import_deal', {
        ...importedDeal,
        name,
        ai_levels: [level, level, level, level, level],
        ai_strategies: [strategy, strategy, strategy, strategy, strategy],
      });
      Renderer.showScreen('game-screen');
    });

    // Join room
    document.getElementById('btn-join-room').addEventListener('click', () => {
      const code = document.getElementById('room-code').value.trim();
      if (code.length !== 6) { alert('Enter a 6-digit room code'); return; }
      const name = document.getElementById('player-name').value.trim() || 'Player';
      currentMode = 'join';
      Connection.emit('join_room_req', { room_id: code, name });
    });

    // Leave room
    document.getElementById('btn-leave-room').addEventListener('click', () => {
      Connection.emit('leave_room_req');
      Renderer.showScreen('start-screen');
    });

    // Join screen: back button
    document.getElementById('btn-back-start').addEventListener('click', () => {
      Renderer.showScreen('start-screen');
    });
  }

  let publicRoomPage = 0;

  function renderPublicRooms(data) {
    const listEl = document.getElementById('public-rooms-list');
    const pagerEl = document.getElementById('public-rooms-pager');
    if (!data.rooms || data.rooms.length === 0) {
      listEl.innerHTML = '<p style="color:#666;text-align:center">No public rooms available</p>';
      pagerEl.innerHTML = '';
      return;
    }
    let html = '<table style="width:100%;font-size:0.85rem;border-collapse:collapse">';
    html += '<tr style="color:var(--clr-gold);border-bottom:1px solid #555"><th>Room</th><th>Host</th><th>Players</th><th></th></tr>';
    data.rooms.forEach(r => {
      html += '<tr style="border-bottom:1px solid #333">';
      html += `<td style="padding:0.4em">${r.room_id}</td>`;
      html += `<td>${r.host}</td>`;
      html += `<td>${r.humans}P / ${r.ais}AI / ${r.empty} open</td>`;
      html += `<td><button class="btn btn-primary btn-small join-public-btn" data-rid="${r.room_id}">Join</button></td>`;
      html += '</tr>';
    });
    html += '</table>';
    listEl.innerHTML = html;

    // Pager
    let phtml = '';
    if (data.page > 0) phtml += `<button class="btn btn-small pub-page-btn" data-page="${data.page - 1}">&lt; Prev</button> `;
    phtml += `<span style="color:#aaa;font-size:0.8rem">Page ${data.page + 1}/${data.pages || 1}</span>`;
    if (data.page < (data.pages || 1) - 1) phtml += ` <button class="btn btn-small pub-page-btn" data-page="${data.page + 1}">Next &gt;</button>`;
    phtml += ` <button class="btn btn-small pub-page-btn" data-page="${data.page}" style="margin-left:0.5em">Refresh</button>`;
    pagerEl.innerHTML = phtml;

    // Bind
    document.querySelectorAll('.join-public-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const name = document.getElementById('player-name').value.trim() || 'Player';
        currentMode = 'join';
        Connection.emit('join_room_req', { room_id: btn.dataset.rid, name });
      });
    });
    document.querySelectorAll('.pub-page-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        Connection.emit('list_public_rooms', { page: parseInt(btn.dataset.page) });
      });
    });
  }

  function bindConnectionEvents() {
    Connection.on('game_state', onGameState);
    Connection.on('error', data => {
      console.warn('[Error]', data.msg);
      Animations.showCenterMessage(data.msg, 2000);
    });
    Connection.on('disconnected', () => {
      console.warn('[Main] Disconnected — will auto-reconnect');
    });
    Connection.on('connected', () => {
      console.log('[Main] Connected');
      // Re-join room on reconnect if we were in a game
      if (currentRoomId && currentMode === 'single') {
        console.log('[Main] Reconnected — re-starting single game');
      }
    });
    Connection.on('deal_data', data => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `napoleon_deal_${new Date().toISOString().slice(0,19).replace(/[:-]/g,'')}.json`;
      a.click();
      URL.revokeObjectURL(url);
    });
    Connection.on('auto_play_state', data => {
      autoPlay = data.auto_play;
      updateAutoPlayBtn();
    });
    Connection.on('room_created', data => {
      currentRoomId = data.room_id;
      currentMode = 'host';
      isHost = true;
      Renderer.showScreen('room-screen');
      document.getElementById('room-code-display').textContent = data.room_id;
    });
    Connection.on('room_joined', data => {
      currentRoomId = data.room_id;
      isHost = false;
      Renderer.showScreen('room-screen');
      document.getElementById('room-code-display').textContent = data.room_id;
    });
    Connection.on('room_state', renderRoomLobby);
    Connection.on('join_error', data => {
      alert(data.msg);
    });
    Connection.on('public_rooms', renderPublicRooms);
    Connection.on('room_closed', data => {
      alert(data.msg);
      Renderer.hideModal();
      document.getElementById('gameover-overlay').classList.remove('active');
      Renderer.showScreen('start-screen');
    });
    Connection.on('deal_imported', data => {
      Animations.showCenterMessage('Deal imported!', 1500);
    });
    Connection.on('skip_vote_status', data => {
      if (data.approved) {
        Animations.showCenterMessage('All agreed — skipping to end!', 1500);
      } else {
        Animations.showCenterMessage(`Skip vote: ${data.voted}/${data.total}`, 2000);
      }
    });
  }

  function updateAutoPlayBtn() {
    const btn = document.getElementById('btn-auto-play');
    if (!btn) return;
    btn.textContent = autoPlay ? 'AI Autopilot: ON' : 'AI Autopilot: OFF';
    btn.classList.toggle('btn-success', autoPlay);
    btn.classList.toggle('btn-danger', !autoPlay);
    const skipBtn = document.getElementById('btn-skip');
    if (skipBtn) skipBtn.style.display = autoPlay ? '' : 'none';
  }

  // ================================================================
  // Room Lobby
  // ================================================================
  function renderRoomLobby(room) {
    const slotsEl = document.getElementById('room-slots');
    const actionsEl = document.getElementById('room-actions');
    const strategies = ['aggressive', 'conservative', 'tactical', 'deceptive'];

    let html = '<table style="width:100%;font-size:0.9rem;border-collapse:collapse">';
    html += '<tr style="color:var(--clr-gold);border-bottom:1px solid #555"><th>Seat</th><th>Player</th><th>Status</th>';
    if (isHost) html += '<th>Action</th>';
    html += '</tr>';

    room.slots.forEach(s => {
      html += '<tr style="border-bottom:1px solid #333">';
      html += `<td style="padding:0.5em">${s.index + 1}</td>`;
      if (s.type === 'empty') {
        html += '<td style="color:#666">Empty</td><td></td>';
        if (isHost) {
          html += `<td style="white-space:nowrap">`;
          html += `<button class="btn btn-small set-ai-btn" data-idx="${s.index}">+ AI</button> `;
          html += `<select class="slot-strategy" data-idx="${s.index}" style="font-size:0.75rem;padding:0.2em;background:#2a2a4a;color:#fff;border:1px solid #555;border-radius:4px">`;
          for (const st of ['Aggressive','Conservative','Tactical','Deceptive']) {
            html += `<option value="${st.toLowerCase()}"${st==='Conservative'?' selected':''}>${st}</option>`;
          }
          html += `</select> `;
          html += `<select class="slot-level" data-idx="${s.index}" style="font-size:0.75rem;padding:0.2em;background:#2a2a4a;color:#fff;border:1px solid #555;border-radius:4px">`;
          html += `<option value="1">Bgn</option><option value="2">Cpt</option><option value="3" selected>Exp</option>`;
          html += `</select>`;
          html += `</td>`;
        }
      } else if (s.type === 'ai') {
        const stratAbbr = {aggressive:'Agg',conservative:'Con',tactical:'Tac',deceptive:'Dec'}[s.ai_strategy] || s.ai_strategy;
        const levelAbbr = {1:'Bgn',2:'Cpt',3:'Exp'}[s.ai_level] || '?';
        html += `<td>${s.name} <span style="color:#888">[${stratAbbr}/${levelAbbr}]</span></td>`;
        html += '<td style="color:var(--clr-success)">Ready</td>';
        if (isHost && s.index > 0) html += `<td><button class="btn btn-danger btn-small vacate-btn" data-idx="${s.index}">Remove</button></td>`;
        else if (isHost) html += '<td></td>';
      } else {
        html += `<td>${s.name}${s.index === 0 ? ' (Host)' : ''}</td>`;
        html += `<td style="color:${s.ready ? 'var(--clr-success)' : '#faa'}">${s.ready ? 'Ready' : 'Not Ready'}</td>`;
        if (isHost && s.index > 0) html += `<td><button class="btn btn-danger btn-small vacate-btn" data-idx="${s.index}">Kick</button></td>`;
        else if (isHost) html += '<td></td>';
      }
      html += '</tr>';
    });
    html += '</table>';
    slotsEl.innerHTML = html;

    // Actions
    let actHtml = '';
    if (isHost) {
      if (room.all_ready && room.all_filled) {
        actHtml += '<button class="btn btn-primary" id="btn-host-start">Start Game</button> ';
      } else {
        actHtml += `<button class="btn btn-primary" disabled>Waiting... (${room.slots.filter(s => s.type !== 'empty' && s.ready).length}/6 ready)</button> `;
      }
      actHtml += `<div style="margin-top:0.5em"><label style="cursor:pointer;font-size:0.85rem;color:#ccc"><input type="checkbox" id="chk-public" ${room.public ? 'checked' : ''}> Public Room</label></div>`;
      actHtml += '<div style="margin-top:0.5em"><label style="cursor:pointer;font-size:0.85rem;color:#aaa">Import deal: <input id="host-import-deal" type="file" accept=".json" style="font-size:0.8rem;color:#ccc"></label></div>';
    } else {
      actHtml += '<button class="btn btn-success" id="btn-ready">Ready</button>';
    }
    actionsEl.innerHTML = actHtml;

    // Bind buttons
    document.querySelectorAll('.set-ai-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = parseInt(btn.dataset.idx);
        const stratEl = document.querySelector(`.slot-strategy[data-idx="${idx}"]`);
        const levelEl = document.querySelector(`.slot-level[data-idx="${idx}"]`);
        const strategy = stratEl ? stratEl.value : 'conservative';
        const level = levelEl ? parseInt(levelEl.value) : 3;
        Connection.emit('set_slot_ai', { index: idx, level, strategy });
      });
    });
    document.querySelectorAll('.vacate-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        Connection.emit('vacate_slot', { index: parseInt(btn.dataset.idx) });
      });
    });
    const chkPublic = document.getElementById('chk-public');
    if (chkPublic) {
      chkPublic.addEventListener('change', () => {
        Connection.emit('set_room_public', { public: chkPublic.checked });
      });
    }
    const startBtn = document.getElementById('btn-host-start');
    if (startBtn) {
      startBtn.addEventListener('click', () => {
        Connection.emit('host_start');
        Renderer.showScreen('game-screen');
      });
    }
    const readyBtn = document.getElementById('btn-ready');
    if (readyBtn) {
      readyBtn.addEventListener('click', () => {
        Connection.emit('player_ready');
      });
    }
    const hostImport = document.getElementById('host-import-deal');
    if (hostImport) {
      hostImport.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
          try {
            const deal = JSON.parse(ev.target.result);
            Connection.emit('host_import_deal', deal);
          } catch { alert('Invalid JSON'); }
        };
        reader.readAsText(file);
      });
    }
  }

  // ================================================================
  // Game State handler
  // ================================================================
  function onGameState(state) {
    currentState = state;
    // Switch to game screen if not already there
    if (document.getElementById('game-screen').classList.contains('active') === false) {
      Renderer.showScreen('game-screen');
    }
    Renderer.updateInfoBar(state);
    Renderer.updateSeats(state);
    Renderer.updateTrickArea(state);

    // Fold table on mobile during non-playing phases
    const table = document.getElementById('game-table');
    const foldPhases = ['bidding', 'choose_trump', 'swap_cards', 'choose_secretary', 'announce'];
    if (table) {
      table.classList.toggle('table-folded', foldPhases.includes(state.phase));
    }

    prevPhase = state.phase;

    switch (state.phase) {
      case 'bidding': handleBidding(state); break;
      case 'choose_trump': handleChooseTrump(state); break;
      case 'swap_cards': handleSwapCards(state); break;
      case 'choose_secretary': handleChooseSecretary(state); break;
      case 'announce': handleAnnounce(state); break;
      case 'playing': handlePlaying(state); break;
      case 'choose_lead_suit': handleChooseLeadSuit(state); break;
      case 'choose_call_joker': handleChooseCallJoker(state); break;
      case 'finished': handleFinished(state); break;
    }
  }

  // ================================================================
  // Phase handlers (same as before, but room-aware)
  // ================================================================
  function handleBidding(state) {
    Renderer.renderHand(state, null);
    Renderer.renderBiddingActions(state, bid => {
      Connection.emit('bid', { bid });
    });
    const histHtml = Renderer.renderBidHistory(state);
    const existing = document.getElementById('bid-history-area');
    if (existing) existing.innerHTML = histHtml;
    else {
      const div = document.createElement('div');
      div.id = 'bid-history-area';
      div.innerHTML = histHtml;
      document.getElementById('action-bar').prepend(div);
    }
  }

  function handleChooseTrump(state) {
    Renderer.renderHand(state, null);
    Renderer.clearActionBar();
    document.getElementById('center-msg').classList.remove('visible');
    if (state.napoleon_idx === state.my_index) {
      Renderer.showTrumpChooser(suit => { Connection.emit('choose_trump', { suit }); });
    } else {
      Renderer.setActionBar('<span>Napoleon is choosing trump suit...</span>');
    }
  }

  function handleSwapCards(state) {
    Renderer.clearActionBar();
    if (state.napoleon_idx === state.my_index) {
      Renderer.showSwapUI(state, discardIds => { Connection.emit('swap_cards', { discard_ids: discardIds }); });
    } else {
      Renderer.renderHand(state, null);
      Renderer.setActionBar('<span>Napoleon is swapping cards...</span>');
    }
  }

  function handleChooseSecretary(state) {
    Renderer.renderHand(state, null);
    Renderer.clearActionBar();
    if (state.napoleon_idx === state.my_index) {
      Renderer.showSecretaryChooser(state, (suit, rank) => { Connection.emit('choose_secretary', { suit, rank }); });
    } else {
      Renderer.setActionBar('<span>Napoleon is choosing secretary card...</span>');
    }
  }

  function handleAnnounce(state) {
    Renderer.renderHand(state, null);
    Renderer.clearActionBar();
    Renderer.showAnnouncement(state, () => { Connection.emit('confirm_announcement'); });
  }

  function handlePlaying(state) {
    Renderer.hideModal();
    const isMyTurn = state.current_player_idx === state.my_index;
    Renderer.renderHand(state, isMyTurn ? cardId => { Connection.emit('play_card', { card_id: cardId }); } : null);

    if (isMyTurn) {
      let actionHtml = '<span style="color:var(--clr-gold)">Your turn — click a highlighted card to play.</span>';
      if (state.uncalled_joker && state.current_player_idx === state.my_index) {
        const jr = state.uncalled_joker;
        const jName = {big1:'Big1(大鬼1)',big2:'Big2(大鬼2)',mid1:'Mid1(中鬼1)',mid2:'Mid2(中鬼2)',small1:'Small1(小鬼1)',small2:'Small2(小鬼2)'}[jr] || jr;
        actionHtml += ` <button class="btn btn-danger btn-small" id="btn-add-call" style="margin-left:1em">Also call ${jName}</button>`;
      }
      Renderer.setActionBar(actionHtml);
      const addCallBtn = document.getElementById('btn-add-call');
      if (addCallBtn) {
        addCallBtn.addEventListener('click', () => { Connection.emit('add_call_joker', { joker_rank: state.uncalled_joker }); });
      }
    } else {
      const name = state.players[state.current_player_idx]?.name || '?';
      Renderer.setActionBar(`<span>${name} is playing...</span>`);
    }
  }

  function handleChooseCallJoker(state) {
    if (state.lead_player_idx === state.my_index) {
      Renderer.showCallJokerChooser(state, jokerRank => { Connection.emit('choose_call_joker', { joker_rank: jokerRank }); });
    }
  }

  function handleChooseLeadSuit(state) {
    if (state.current_player_idx === state.my_index || state.my_index === state.lead_player_idx) {
      Renderer.showLeadSuitChooser(suit => { Connection.emit('choose_lead_suit', { suit }); });
    }
  }

  function handleFinished(state) {
    Renderer.renderHand(state, null);
    Renderer.clearActionBar();
    Renderer.showGameOver(state, null, () => {
      // New Game
      autoPlay = false;
      updateAutoPlayBtn();
      if (currentMode === 'single') {
        const name = document.getElementById('player-name')?.value?.trim() || 'Player';
        const level = parseInt(document.getElementById('ai-level')?.value || '3', 10);
        const strategy = document.getElementById('ai-strategy')?.value || 'conservative';
        Connection.emit('start_game', { name, ai_levels: [level,level,level,level,level], ai_strategies: [strategy,strategy,strategy,strategy,strategy] });
      } else {
        Renderer.showScreen('room-screen');
      }
    });
  }
})();

/**
 * Renderer — builds and updates all DOM for the game.
 * Keeps rendering pure (no socket calls). main.js wires events.
 */

const Renderer = (() => {
  const SUIT_SYM = { spades: '♠', hearts: '♥', diamonds: '♦', clubs: '♣' };
  const SUIT_NAMES = { spades: '黑桃', hearts: '紅心', diamonds: '方塊', clubs: '梅花' };
  const JOKER_DISPLAY = {
    big1: '大鬼1', big2: '大鬼2',
    mid1: '中鬼1', mid2: '中鬼2',
    small1: '小鬼1', small2: '小鬼2',
  };

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return document.querySelectorAll(sel); }

  const RANK_ORDER = {'2':0,'3':1,'4':2,'5':3,'6':4,'7':5,'8':6,'9':7,'10':8,'J':9,'Q':10,'K':11,'A':12};
  const JOKER_ORDER = {big1:6,big2:5,mid1:4,mid2:3,small1:2,small2:1};

  /** Sort cards: jokers first (big→small), trump suit next (A→2), then other suits (A→2). All descending. */
  function sortCards(cards, trumpSuit) {
    return [...cards].sort((a, b) => {
      const aKey = _cardSortKey(a, trumpSuit);
      const bKey = _cardSortKey(b, trumpSuit);
      // Compare tuple-like: higher group first, then higher rank first
      for (let i = 0; i < aKey.length; i++) {
        if (aKey[i] !== bKey[i]) return bKey[i] - aKey[i];
      }
      return 0;
    });
  }

  function _cardSortKey(c, trumpSuit) {
    // group: 3=joker, 2=trump, 1=non-trump; rank descending; deck tiebreak
    if (c.is_joker) return [3, JOKER_ORDER[c.rank] || 0, 0];
    const group = c.suit === trumpSuit ? 2 : 1;
    const suitOrd = {spades:4, hearts:3, diamonds:2, clubs:1}[c.suit] || 0;
    return [group, suitOrd, RANK_ORDER[c.rank] || 0];
  }

  // ================================================================
  // Card HTML
  // ================================================================
  function cardHTML(card, extra = '') {
    if (card.is_joker) {
      const label = JOKER_DISPLAY[card.rank] || card.rank;
      return `<div class="card" data-card-id="${card.id}" data-suit="joker" data-rank="${card.rank}" ${extra}>
        <span class="card-rank" style="font-size:0.75rem">${label}</span>
        <span class="card-suit">🃏</span>
      </div>`;
    }
    const sym = SUIT_SYM[card.suit] || '';
    return `<div class="card" data-card-id="${card.id}" data-suit="${card.suit}" data-rank="${card.rank}" ${extra}>
      <span class="card-corner">${card.rank}<br>${sym}</span>
      <span class="card-suit">${sym}</span>
      <span class="card-rank">${card.rank}</span>
      <span class="card-corner-br">${card.rank}<br>${sym}</span>
    </div>`;
  }

  // ================================================================
  // Info Bar
  // ================================================================
  function _secretaryDisplay(sc) {
    if (!sc || !sc.suit) return '';
    return sc.suit === 'joker'
      ? JOKER_DISPLAY[sc.rank] || sc.rank
      : `${SUIT_SYM[sc.suit] || ''}${sc.rank}`;
  }

  function updateInfoBar(state) {
    const phaseLabels = {
      waiting: '等待中',
      bidding: '喊牌',
      choose_trump: '選王牌',
      swap_cards: '換牌',
      choose_secretary: '選秘書牌',
      announce: '公告',
      playing: '出牌',
      choose_lead_suit: '指定花色',
      finished: '結束',
    };
    $('#info-round').textContent = `回合: ${state.current_round || '-'}`;
    $('#info-trump').innerHTML = state.trump_suit
      ? `王牌: <span style="font-size:1.2em">${SUIT_SYM[state.trump_suit] || ''}</span> ${SUIT_NAMES[state.trump_suit] || ''}`
      : '王牌: -';
    $('#info-contract').textContent = `合約: ${state.contract_points || '-'}`;
    $('#info-nap-pts').textContent = `拿破崙: ${state.napoleon_points}`;
    $('#info-un-pts').textContent = `聯合國: ${state.un_points}`;
    $('#info-phase').textContent = phaseLabels[state.phase] || state.phase;

    // Secretary card display (public info once declared)
    let secEl = $('#info-secretary');
    if (!secEl) {
      secEl = document.createElement('div');
      secEl.id = 'info-secretary';
      secEl.className = 'info-item';
      $('.info-bar').appendChild(secEl);
    }
    if (state.secretary_card && state.secretary_card.suit) {
      secEl.innerHTML = `秘書牌: <strong style="color:var(--clr-gold)">${_secretaryDisplay(state.secretary_card)}</strong>`;
      secEl.style.display = '';
    } else {
      secEl.style.display = 'none';
    }

    // Called jokers display
    let callEl = $('#info-called-jokers');
    if (!callEl) {
      callEl = document.createElement('div');
      callEl.id = 'info-called-jokers';
      callEl.className = 'info-item';
      $('.info-bar').appendChild(callEl);
    }
    const called = state.called_jokers || [];
    if (called.length > 0) {
      const names = called.map(r => JOKER_DISPLAY[r] || r).join(', ');
      callEl.innerHTML = `請鬼: <strong style="color:var(--clr-danger)">${names}</strong>`;
      callEl.style.display = '';
    } else {
      callEl.style.display = 'none';
    }
  }

  // ================================================================
  // Seats
  // ================================================================
  function updateSeats(state) {
    state.players.forEach(p => {
      const seat = $(`.seat[data-seat="${p.index}"]`);
      if (!seat) return;
      const nameEl = seat.querySelector('.seat-name');
      const infoEl = seat.querySelector('.seat-info');
      const countEl = seat.querySelector('.seat-card-count');

      let label = p.name;
      if (p.index === state.my_index) label += ' (You)';
      nameEl.textContent = label;

      let roleStr = '';
      if (p.role === 'napoleon') roleStr = '👑 Napoleon';
      else if (p.role === 'secretary') roleStr = '📋 Secretary';
      else if (p.role === 'united_nations') roleStr = '🌐 UN';
      infoEl.textContent = roleStr;

      countEl.textContent = `${p.hand_count} cards | ${p.points_won} pts`;
      seat.setAttribute('data-active', p.index === state.current_player_idx ? 'true' : 'false');
      seat.setAttribute('data-role', p.role);
    });
  }

  // ================================================================
  // Trick Area
  // ================================================================
  function updateTrickArea(state) {
    // Clear all trick positions
    for (let i = 0; i < 6; i++) {
      const el = $(`.trick-card[data-trick-seat="${i}"]`);
      if (el) el.innerHTML = '';
    }
    // Place cards
    (state.current_trick || []).forEach(([pidx, card]) => {
      const el = $(`.trick-card[data-trick-seat="${pidx}"]`);
      if (el) {
        const secAttr = _isSecretaryCard(card, state) ? 'data-secretary="true"' : '';
        el.innerHTML = cardHTML(card, secAttr);
        Animations.popIn(el.firstElementChild);
      }
    });
  }

  // ================================================================
  // Hand
  // ================================================================
  function _isSecretaryCard(card, state) {
    const sc = state.secretary_card;
    if (!sc) return false;
    // Match by specific card ID if available
    if (sc.id && card.id) return card.id === sc.id;
    // Fallback: match by type (for display purposes like info bar)
    return sc.suit && card.suit === sc.suit && card.rank === sc.rank;
  }

  /** Should this card in the player's hand be highlighted as secretary? */
  function _showSecretaryHighlight(card, state) {
    if (!_isSecretaryCard(card, state)) return false;
    // Napoleon's own copies: hide highlight if other players hold the card
    if (state.hide_secretary_highlight) return false;
    return true;
  }

  function _buildHandStats(cards, trumpSuit) {
    const pointRanks = new Set(['J', 'Q', 'K', 'A']);
    const stats = {};
    let jokerCount = 0;
    for (const c of cards) {
      if (c.is_joker) { jokerCount++; continue; }
      if (!stats[c.suit]) stats[c.suit] = { count: 0, pts: 0 };
      stats[c.suit].count++;
      if (pointRanks.has(c.rank)) stats[c.suit].pts++;
    }
    // Order: trump first, then spades/hearts/diamonds/clubs
    const order = [trumpSuit, ...['spades','hearts','diamonds','clubs'].filter(s => s !== trumpSuit)];
    let html = '';
    if (jokerCount > 0) {
      html += `<span class="hand-stat"><span class="suit-icon" data-suit="joker">🃏</span><span class="stat-count">${jokerCount}</span></span>`;
    }
    for (const suit of order) {
      const s = stats[suit];
      if (!s) continue;
      const isTrump = suit === trumpSuit;
      const cls = isTrump ? 'hand-stat is-trump' : 'hand-stat';
      html += `<span class="${cls}"><span class="suit-icon" data-suit="${suit}">${SUIT_SYM[suit]}</span>`;
      html += `<span class="stat-count">${s.count}</span>`;
      if (s.pts > 0) html += `<span class="stat-pts">(${s.pts}pt)</span>`;
      html += `</span>`;
    }
    const total = cards.length;
    const totalPts = cards.filter(c => !c.is_joker && pointRanks.has(c.rank)).length;
    html += `<span class="hand-stat"><span style="color:#aaa">Total</span><span class="stat-count">${total}</span><span class="stat-pts">(${totalPts}pt)</span></span>`;
    return html;
  }

  let _selectedSuitTab = null;

  function _isMobile() {
    return window.innerWidth <= 768;
  }

  function _autoSelectSuit(state) {
    const hand = state.hand || [];
    const trump = state.trump_suit;
    const lead = state.lead_suit;
    const hasSuit = (s) => hand.some(c => s === 'joker' ? c.is_joker : (!c.is_joker && c.suit === s));

    // Priority: lead suit > trump > first available
    if (lead && hasSuit(lead)) return lead;
    if (trump && hasSuit(trump)) return trump;
    for (const s of ['spades','hearts','diamonds','clubs']) {
      if (hasSuit(s)) return s;
    }
    if (hasSuit('joker')) return 'joker';
    return null;
  }

  function renderHand(state, onCardClick) {
    const container = $('#hand-cards');
    container.innerHTML = '';
    const statsEl = $('#hand-stats');
    const playable = new Set(state.playable_ids || []);
    const isMyTurn = state.phase === 'playing' && state.current_player_idx === state.my_index;
    const sorted = sortCards(state.hand, state.trump_suit);
    const mobile = _isMobile();

    // Stats bar — also serves as suit tabs on mobile
    if (statsEl) {
      if (mobile && state.phase === 'playing') {
        statsEl.innerHTML = _buildSuitTabs(state);
      } else {
        statsEl.innerHTML = _buildHandStats(state.hand, state.trump_suit);
      }
    }

    // Auto-select suit on mobile
    if (mobile && state.phase === 'playing') {
      if (!_selectedSuitTab || !state.hand.some(c =>
        _selectedSuitTab === 'joker' ? c.is_joker : (!c.is_joker && c.suit === _selectedSuitTab)
      )) {
        _selectedSuitTab = _autoSelectSuit(state);
      }
    }

    sorted.forEach(card => {
      // On mobile during play, filter by selected suit tab
      if (mobile && state.phase === 'playing' && _selectedSuitTab) {
        const cardSuit = card.is_joker ? 'joker' : card.suit;
        if (cardSuit !== _selectedSuitTab) return;
      }

      const canPlay = isMyTurn && playable.has(card.id);
      let attrs = canPlay ? 'data-playable="true"' : '';
      if (_showSecretaryHighlight(card, state)) attrs += ' data-secretary="true"';
      const div = document.createElement('div');
      div.innerHTML = cardHTML(card, attrs);
      const cardEl = div.firstElementChild;
      if (canPlay && onCardClick) {
        cardEl.addEventListener('click', () => onCardClick(card.id));
      }
      container.appendChild(cardEl);
    });

    // Bind suit tab clicks
    if (mobile && state.phase === 'playing') {
      $$('.suit-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          _selectedSuitTab = btn.dataset.suit;
          renderHand(state, onCardClick);
        });
      });
    }
  }

  function _buildSuitTabs(state) {
    const hand = state.hand || [];
    const trump = state.trump_suit;
    const pointRanks = new Set(['J','Q','K','A']);
    const suits = {};
    let jokerCount = 0;
    hand.forEach(c => {
      if (c.is_joker) { jokerCount++; return; }
      if (!suits[c.suit]) suits[c.suit] = { count: 0, pts: 0 };
      suits[c.suit].count++;
      if (pointRanks.has(c.rank)) suits[c.suit].pts++;
    });

    const order = [trump, ...['spades','hearts','diamonds','clubs'].filter(s => s !== trump)];
    let html = '';

    if (jokerCount > 0) {
      const sel = _selectedSuitTab === 'joker' ? ' suit-tab-active' : '';
      html += `<button class="suit-tab-btn${sel}" data-suit="joker"><span class="suit-icon" data-suit="joker">🃏</span>${jokerCount}</button>`;
    }
    for (const suit of order) {
      const s = suits[suit];
      if (!s) continue;
      const sel = _selectedSuitTab === suit ? ' suit-tab-active' : '';
      const isTrump = suit === trump;
      html += `<button class="suit-tab-btn${sel}${isTrump ? ' is-trump' : ''}" data-suit="${suit}">`;
      html += `<span class="suit-icon" data-suit="${suit}">${SUIT_SYM[suit]}</span>`;
      html += `${s.count}`;
      if (s.pts > 0) html += `<span class="stat-pts">(${s.pts})</span>`;
      html += `</button>`;
    }
    return html;
  }

  // ================================================================
  // Action Bar
  // ================================================================
  function setActionBar(html) {
    $('#action-bar').innerHTML = html;
  }

  function clearActionBar() {
    $('#action-bar').innerHTML = '';
  }

  // ================================================================
  // Bidding UI
  // ================================================================
  function renderBiddingActions(state, onBid) {
    const isMyTurn = state.current_bidder_idx === state.my_index;
    if (!isMyTurn) {
      const bidderName = state.players[state.current_bidder_idx]?.name || '?';
      setActionBar(`<span>${bidderName} is bidding...</span>`);
      return;
    }
    const minBid = Math.max(23, state.highest_bid + 1);
    setActionBar(`
      <div class="bid-controls">
        <span>Min: ${minBid}</span>
        <input id="bid-input" type="number" min="${minBid}" max="48" value="${minBid}">
        <button class="btn btn-primary btn-small" id="btn-bid">Bid</button>
        <button class="btn btn-danger btn-small" id="btn-pass">Pass</button>
      </div>
    `);
    $('#btn-bid').addEventListener('click', () => {
      console.log('[BID] Bid button clicked');
      const val = parseInt($('#bid-input').value, 10);
      if (val >= minBid && val <= 48) onBid(val);
    });
    $('#btn-pass').addEventListener('click', () => {
      console.log('[BID] Pass button clicked');
      onBid(0);
    });
  }

  function renderBidHistory(state) {
    let html = '<div class="bid-history">';
    (state.bid_history || []).forEach(entry => {
      const name = state.players[entry.player]?.name || '?';
      if (entry.bid === 'pass') {
        html += `<span class="bid-tag pass">${name}: Pass</span>`;
      } else {
        html += `<span class="bid-tag bid">${name}: ${entry.bid}</span>`;
      }
    });
    html += '</div>';
    return html;
  }

  // ================================================================
  // Modal helpers
  // ================================================================
  function showModal(html) {
    const overlay = $('#modal-overlay');
    const content = $('#modal-content');
    content.innerHTML = html;
    overlay.classList.add('active');
    Animations.fadeIn(content);
  }

  function hideModal() {
    $('#modal-overlay').classList.remove('active');
  }

  // ================================================================
  // Choose Trump UI
  // ================================================================
  function showTrumpChooser(onChoose) {
    let html = '<h2>Choose Trump Suit</h2><div class="suit-picker">';
    for (const suit of ['spades', 'hearts', 'diamonds', 'clubs']) {
      html += `<button class="suit-btn" data-suit="${suit}">${SUIT_SYM[suit]}<br><small>${SUIT_NAMES[suit]}</small></button>`;
    }
    html += '</div>';
    showModal(html);
    $$('.suit-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        hideModal();
        onChoose(btn.dataset.suit);
      });
    });
  }

  // ================================================================
  // Swap Cards UI
  // ================================================================
  function showSwapUI(state, onConfirm) {
    const handCards = sortCards(state.hand, state.trump_suit);
    const bottomCards = sortCards(state.bottom_cards || [], state.trump_suit);
    const allCards = [...handCards, ...bottomCards];
    const bottomIds = new Set(bottomCards.map(c => c.id));
    const selected = new Set();
    const pointRanks = new Set(['J', 'Q', 'K', 'A']);

    function render() {
      const selPoints = allCards.filter(c => selected.has(c.id) && !c.is_joker && pointRanks.has(c.rank)).length;
      // Cards that will remain in hand after discard
      const keepCards = allCards.filter(c => !selected.has(c.id));

      let html = '<h2>Discard Cards</h2>';
      html += '<p>Select any 12 cards to discard from hand + bottom cards combined.</p>';

      const count = selected.size;
      const cls = count === 12 ? 'ok' : 'not-ok';
      html += `<div class="discard-count" style="margin:0.5em 0">Discard: <span class="${cls}">${count}/12</span>`;
      if (selPoints > 0) {
        html += ` <span style="color:var(--clr-danger);margin-left:0.5em">(${selPoints} point cards => UN gets ${selPoints} pts)</span>`;
      }
      html += `</div>`;

      // Stats for cards that will remain
      html += `<div style="margin:0.3em 0"><span style="color:#aaa;font-size:0.8rem">Remaining hand stats: </span><span class="hand-stats" style="display:inline-flex">${_buildHandStats(keepCards, state.trump_suit)}</span></div>`;

      html += `<div class="swap-section"><h3>Bottom Cards (${bottomCards.length})</h3>`;
      html += `<div class="hand-stats">${_buildHandStats(bottomCards, state.trump_suit)}</div>`;
      html += '<div class="card-grid">';
      bottomCards.forEach(c => {
        const sel = selected.has(c.id) ? 'data-selected="true"' : '';
        html += cardHTML(c, `data-playable="true" ${sel}`);
      });
      html += '</div></div>';

      html += `<div class="swap-section"><h3>Your Hand (${handCards.length})</h3>`;
      html += `<div class="hand-stats">${_buildHandStats(handCards, state.trump_suit)}</div>`;
      html += '<div class="card-grid">';
      handCards.forEach(c => {
        const sel = selected.has(c.id) ? 'data-selected="true"' : '';
        html += cardHTML(c, `data-playable="true" ${sel}`);
      });
      html += '</div></div>';

      // Change trump option
      html += `<div class="change-trump-section">
        <h3>Change Trump? (penalty: contract +3)</h3>
        <p class="warning">Current: ${SUIT_SYM[state.trump_suit]} ${SUIT_NAMES[state.trump_suit]}</p>
        <div class="suit-picker">`;
      for (const suit of ['spades', 'hearts', 'diamonds', 'clubs']) {
        html += `<button class="suit-btn change-trump-btn" data-suit="${suit}">${SUIT_SYM[suit]}</button>`;
      }
      html += '</div></div>';

      html += `<button class="btn btn-primary" id="btn-confirm-swap" ${count === 12 ? '' : 'disabled'}>Confirm Discard</button>`;
      showModal(html);

      // Bind card clicks — ALL cards (hand + bottom) are selectable
      $$('#modal-content .card-grid .card[data-playable]').forEach(el => {
        const cid = el.dataset.cardId;
        el.addEventListener('click', () => {
          if (selected.has(cid)) selected.delete(cid);
          else if (selected.size < 12) selected.add(cid);
          render();
        });
      });

      // Change trump buttons
      $$('.change-trump-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          Connection.emit('change_trump', { suit: btn.dataset.suit });
        });
      });

      const confirmBtn = $('#btn-confirm-swap');
      if (confirmBtn && !confirmBtn.disabled) {
        confirmBtn.addEventListener('click', () => {
          hideModal();
          onConfirm(Array.from(selected));
        });
      }
    }
    render();
  }

  // ================================================================
  // Choose Secretary UI
  // ================================================================
  function showSecretaryChooser(state, onChoose) {
    const choices = state.valid_secretary_choices || [];
    const nonJoker = choices.filter(c => c.suit !== 'joker');
    const jokers = choices.filter(c => c.suit === 'joker');
    let selected = choices[0] || null;

    function render() {
      let html = '<h2>Choose Secretary Card</h2>';
      html += '<p>You must hold 2 copies of the declared card. Choose from the available options:</p>';

      if (nonJoker.length === 0 && jokers.length === 0) {
        html += '<p style="color:var(--clr-danger)">No valid secretary card choices available!</p>';
        showModal(html);
        return;
      }

      // Group non-joker by suit
      html += '<div class="card-grid" style="margin:1em 0">';
      const sorted = sortCards(nonJoker.map(c => ({...c, is_joker: false, id: c.suit+'_'+c.rank})), state.trump_suit);
      sorted.forEach(ch => {
        const isSel = selected && selected.suit === ch.suit && selected.rank === ch.rank;
        const selAttr = isSel ? 'data-selected="true"' : '';
        const sym = SUIT_SYM[ch.suit] || '';
        html += `<div class="card sec-choice" data-suit="${ch.suit}" data-rank="${ch.rank}" data-playable="true" ${selAttr}>
          <span class="card-suit">${sym}</span>
          <span class="card-rank">${ch.rank}</span>
        </div>`;
      });
      html += '</div>';

      if (jokers.length > 0) {
        html += '<h3>Jokers</h3><div class="card-grid" style="margin:0.5em 0">';
        jokers.forEach(ch => {
          const isSel = selected && selected.suit === 'joker' && selected.rank === ch.rank;
          const selAttr = isSel ? 'data-selected="true"' : '';
          html += `<div class="card sec-choice" data-suit="joker" data-rank="${ch.rank}" data-playable="true" ${selAttr}>
            <span class="card-rank" style="font-size:0.75rem">${JOKER_DISPLAY[ch.rank]}</span>
            <span class="card-suit">🃏</span>
          </div>`;
        });
        html += '</div>';
      }

      // Preview + self-secretary warning
      if (selected) {
        const preview = selected.suit === 'joker'
          ? JOKER_DISPLAY[selected.rank]
          : `${SUIT_SYM[selected.suit]}${selected.rank}`;
        html += `<p style="margin:1em 0;font-size:1.3rem">Secretary: <strong style="color:var(--clr-gold)">${preview}</strong></p>`;
        // Check self_secretary flag from the original choices data
        const match = choices.find(c => c.suit === selected.suit && c.rank === selected.rank);
        if (match && match.self_secretary) {
          html += `<div style="background:rgba(231,76,60,0.2);border:2px solid var(--clr-danger);border-radius:8px;padding:0.8em;margin:0.5em 0">
            <p style="color:var(--clr-danger);font-weight:700;font-size:1.1rem">Warning: No other player holds this card!</p>
            <p style="color:#faa;font-size:0.9rem">You will be playing solo (Napoleon = Secretary).</p>
          </div>`;
        }
      }
      html += `<button class="btn btn-primary" id="btn-confirm-sec" ${selected ? '' : 'disabled'}>Confirm</button>`;
      showModal(html);

      $$('.sec-choice').forEach(el => {
        el.addEventListener('click', () => {
          selected = { suit: el.dataset.suit, rank: el.dataset.rank};
          render();
        });
      });
      const btn = $('#btn-confirm-sec');
      if (btn && selected) {
        btn.addEventListener('click', () => { hideModal(); onChoose(selected.suit, selected.rank); });
      }
    }
    render();
  }

  // ================================================================
  // Announcement Popup
  // ================================================================
  function showAnnouncement(state, onConfirm) {
    const napName = state.players[state.napoleon_idx]?.name || '?';
    const trumpSym = SUIT_SYM[state.trump_suit] || '';
    const trumpName = SUIT_NAMES[state.trump_suit] || '';
    const secDisplay = _secretaryDisplay(state.secretary_card);

    let html = '<h2>Napoleon Declaration</h2>';
    html += `<div style="font-size:1.1rem; line-height:2; margin:1em 0">`;
    html += `<p><strong>${napName}</strong> is Napoleon!</p>`;
    html += `<p>Trump Suit: <span style="font-size:1.6em">${trumpSym}</span> ${trumpName}</p>`;
    html += `<p>Secretary Card: <strong style="color:var(--clr-gold);font-size:1.3em">${secDisplay}</strong></p>`;
    html += `<p>Contract: <strong>${state.contract_points}</strong> points</p>`;
    if (state.discarded_points && state.discarded_points.length > 0) {
      const dp = state.discarded_points;
      const labels = dp.map(c => c.is_joker ? (JOKER_DISPLAY[c.rank]||c.rank) : `${SUIT_SYM[c.suit]||''}${c.rank}`).join('  ');
      html += `<p style="color:var(--clr-danger)">Discarded ${dp.length} point card(s) → UN +${dp.length}pts</p>`;
      html += `<div class="card-grid" style="margin:0.3em 0;justify-content:center">`;
      dp.forEach(c => { html += cardHTML(c); });
      html += `</div>`;
    }
    html += `</div>`;
    html += '<button class="btn btn-primary" id="btn-confirm-announce">Confirm</button>';
    showModal(html);

    $('#btn-confirm-announce').addEventListener('click', () => {
      hideModal();
      onConfirm();
    });
  }

  // ================================================================
  // Choose Lead Suit UI
  // ================================================================
  function showLeadSuitChooser(onChoose) {
    let html = '<h2>Specify Lead Suit</h2><p>You led with a Joker/Secretary card. Choose the suit for this trick.</p>';
    html += '<div class="suit-picker">';
    for (const suit of ['spades','hearts','diamonds','clubs']) {
      html += `<button class="suit-btn" data-suit="${suit}">${SUIT_SYM[suit]}<br><small>${SUIT_NAMES[suit]}</small></button>`;
    }
    html += '</div>';
    showModal(html);
    $$('.suit-btn').forEach(btn => {
      btn.addEventListener('click', () => { hideModal(); onChoose(btn.dataset.suit); });
    });
  }

  // ================================================================
  // Choose Call Joker UI
  // ================================================================
  function showCallJokerChooser(state, onChoose) {
    const jtype = state.pending_call_joker_type; // 'big', 'mid', or 'small'
    const labels = { big: ['Big Joker 1 (大鬼1)', 'Big Joker 2 (大鬼2)'],
                     mid: ['Mid Joker 1 (中鬼1)', 'Mid Joker 2 (中鬼2)'],
                     small: ['Small Joker 1 (小鬼1)', 'Small Joker 2 (小鬼2)'] };
    const ranks = { big: ['big1', 'big2'], mid: ['mid1', 'mid2'], small: ['small1', 'small2'] };
    const names = labels[jtype] || ['Joker 1', 'Joker 2'];
    const rks = ranks[jtype] || ['1', '2'];

    let html = '<h2>Call Joker</h2>';
    html += '<p>Choose which joker to call out (one per round):</p>';
    html += '<div style="display:flex;gap:1em;justify-content:center;margin:1em 0">';
    for (let i = 0; i < 2; i++) {
      html += `<button class="btn btn-primary call-joker-btn" data-rank="${rks[i]}" style="padding:1em 1.5em;font-size:1rem">${names[i]}</button>`;
    }
    html += '</div>';
    showModal(html);
    $$('.call-joker-btn').forEach(btn => {
      btn.addEventListener('click', () => { hideModal(); onChoose(btn.dataset.rank); });
    });
  }

  // ================================================================
  // Game Over
  // ================================================================
  function showGameOver(state, lastResult, onRestart) {
    const overlay = $('#gameover-overlay');
    const content = $('#gameover-content');
    const isNap = state.winner === 'napoleon';
    const winClass = isNap ? 'winner-nap' : 'winner-un';
    const winLabel = isNap ? '👑 Napoleon Wins!' : '🌐 United Nations Wins!';

    let html = `<h1 class="${winClass}">${winLabel}</h1>`;
    html += `<p>Contract: ${state.contract_points} pts</p>`;
    html += `<p>Napoleon Team: ${state.napoleon_points} pts</p>`;
    html += `<p>United Nations: ${state.un_points} pts</p>`;

    if (state.secretary_card) {
      const sc = state.secretary_card;
      const display = sc.suit === 'joker'
        ? JOKER_DISPLAY[sc.rank]
        : `${SUIT_SYM[sc.suit]}${sc.rank}`;
      html += `<p>Secretary Card: ${display}</p>`;
    }
    if (state.secretary_indices && state.secretary_indices.length > 0) {
      const names = state.secretary_indices.map(i => state.players[i]?.name).join(', ');
      html += `<p>Secretary: ${names}</p>`;
    }

    // Player results
    html += '<div style="margin-top:1em">';
    state.players.forEach(p => {
      const role = p.role === 'napoleon' ? '👑' : p.role === 'secretary' ? '📋' : '🌐';
      html += `<p>${role} ${p.name}: ${p.points_won} pts</p>`;
    });
    html += '</div>';

    html += '<div style="margin-top:1.5em;display:flex;gap:1em;justify-content:center">';
    html += '<button class="btn btn-primary" id="btn-replay">Review Game</button>';
    html += '<button class="btn btn-success" id="btn-replay-same">Replay Same Deal</button>';
    html += '<button class="btn btn-success" id="btn-restart">New Game</button>';
    html += '</div>';
    html += '<div style="margin-top:0.8em;display:flex;gap:1em;justify-content:center">';
    html += '<button class="btn btn-small" id="btn-save-deal" style="background:#555">Save Deal</button>';
    html += '<button class="btn btn-danger btn-small" id="btn-end-game">End Game</button>';
    html += '</div>';
    content.innerHTML = html;
    overlay.classList.add('active');

    $('#btn-restart').addEventListener('click', () => {
      overlay.classList.remove('active');
      onRestart();
    });
    $('#btn-end-game').addEventListener('click', () => {
      overlay.classList.remove('active');
      hideModal();
      showScreen('start-screen');
    });
    $('#btn-save-deal').addEventListener('click', () => {
      Connection.emit('save_deal');
    });
    $('#btn-replay-same').addEventListener('click', () => {
      overlay.classList.remove('active');
      Connection.emit('replay_same');
    });
    $('#btn-replay').addEventListener('click', () => {
      overlay.classList.remove('active');
      showReplay(state, onRestart);
    });
  }

  // ================================================================
  // Replay Viewer
  // ================================================================
  function showReplay(state, onRestart) {
    const replay = state.replay;
    if (!replay) return;
    const tricks = replay.tricks || [];
    let currentView = 'hands';
    let trickIdx = 0;

    function renderReplay() {
      let html = '<div style="max-width:900px;margin:0 auto">';
      html += '<h2 style="color:var(--clr-gold);text-align:center;margin-bottom:0.5em">Game Review</h2>';

      // Nav tabs
      html += '<div style="display:flex;gap:0.5em;justify-content:center;margin-bottom:1em;flex-wrap:wrap">';
      for (const [key, label] of [['initial','Initial Hands'],['hands','Starting Hands'],['strategy','Strategy'],['all','All Rounds']]) {
        const active = currentView === key || (currentView === 'round' && key === 'all');
        const cls = active ? 'btn-primary' : 'btn-small';
        html += `<button class="btn ${cls} btn-small replay-nav" data-view="${key}">${label}</button>`;
      }
      html += '</div>';

      if (currentView === 'initial') html += _renderInitialHands(replay, state);
      else if (currentView === 'hands') html += _renderStartingHands(replay, state);
      else if (currentView === 'strategy') html += _renderStrategyGuide(replay, state);
      else if (currentView === 'all') html += _renderAllTricks(tricks, state);
      else if (currentView === 'round') html += _renderRoundAnalysis(tricks, trickIdx, replay, state);

      // Prev/Next + back for round view
      if (currentView === 'round') {
        html += '<div style="text-align:center;margin-top:0.8em;display:flex;gap:0.5em;justify-content:center">';
        if (trickIdx > 0) html += '<button class="btn btn-small replay-prev">&lt; Prev</button>';
        html += '<button class="btn btn-small replay-nav" data-view="all">All Rounds</button>';
        if (trickIdx < tricks.length - 1) html += '<button class="btn btn-small replay-next">Next &gt;</button>';
        html += '</div>';
      }

      html += '<div style="text-align:center;margin-top:1em">';
      html += '<button class="btn btn-danger btn-small" id="replay-close">Close Review</button>';
      html += '</div></div>';

      showModal(html);

      $$('.replay-nav').forEach(btn => {
        btn.addEventListener('click', () => {
          currentView = btn.dataset.view;
          renderReplay();
        });
      });
      // Clickable R1-R25 in all-rounds table
      $$('.replay-round-link').forEach(td => {
        td.addEventListener('click', () => {
          currentView = 'round';
          trickIdx = parseInt(td.dataset.ridx);
          renderReplay();
        });
      });
      const prevBtn = $('.replay-prev');
      if (prevBtn) prevBtn.addEventListener('click', () => { trickIdx--; renderReplay(); });
      const nextBtn = $('.replay-next');
      if (nextBtn) nextBtn.addEventListener('click', () => { trickIdx++; renderReplay(); });
      $('#replay-close').addEventListener('click', () => {
        hideModal();
        showGameOver(state, null, onRestart);
      });
    }
    renderReplay();
  }

  function _renderAllTricks(tricks, state) {
    // Build a map: player index -> column order (lead player first per trick varies, but table has fixed columns)
    const playerOrder = [0, 1, 2, 3, 4, 5];

    let html = '<div style="overflow-x:auto">';
    html += '<table class="replay-table">';

    // Header
    html += '<thead><tr>';
    html += '<th>Round</th><th>Suit</th>';
    playerOrder.forEach(pidx => {
      const p = state.players[pidx];
      let icon = '';
      if (p.role === 'napoleon') icon = ' 👑';
      else if (p.role === 'secretary') icon = ' 📋';
      html += `<th>${p.name}${icon}</th>`;
    });
    html += '<th>Pts</th><th>Score</th>';
    html += '</tr></thead>';

    // Body
    html += '<tbody>';
    // Start with discarded point cards (UN gets those at swap time)
    const discardedPts = (state.replay?.discarded_cards || []).filter(c => c.is_point).length;
    let napRunning = 0, unRunning = discardedPts;
    let secRevealedSoFar = false;
    let secAccumulated = 0; // secretary's undercover points

    // Show discard row if any
    if (discardedPts > 0) {
      html += `<tr class="replay-row-even"><td style="color:#aaa">-</td><td></td>`;
      for (let p = 0; p < 6; p++) html += '<td></td>';
      html += `<td class="replay-pts" style="color:var(--clr-danger)">+${discardedPts}</td>`;
      html += `<td class="replay-score"><span class="replay-nap-score">N:0</span> <span class="replay-un-score">U:${discardedPts}</span> <span style="color:#aaa;font-size:0.65rem">discard</span></td></tr>`;
    }

    tricks.forEach((trick, i) => {
      const winnerP = state.players[trick.winner];
      const winnerRole = winnerP?.role || 'unknown';

      const justRevealed = trick.secretary_revealed && !secRevealedSoFar;
      secRevealedSoFar = trick.secretary_revealed;

      // Transfer secretary's accumulated points on reveal
      if (justRevealed) {
        napRunning += secAccumulated;
        unRunning -= secAccumulated;
      }

      const isNapWin = winnerRole === 'napoleon' || (winnerRole === 'secretary' && secRevealedSoFar);
      if (isNapWin) {
        napRunning += trick.points;
      } else {
        unRunning += trick.points;
        if (winnerRole === 'secretary' && !secRevealedSoFar) secAccumulated += trick.points;
      }

      const leadSuitSym = SUIT_SYM[trick.lead_suit] || '';
      // Check if lead card is joker/secretary (declared suit)
      const leadCard = trick.cards[0]?.[1];
      const isDeclared = leadCard && (leadCard.is_joker || _isSecretaryCard(leadCard, state));

      const rowCls = i % 2 === 0 ? 'replay-row-even' : 'replay-row-odd';
      html += `<tr class="${rowCls}">`;
      html += `<td class="replay-round replay-round-link" data-ridx="${i}" style="cursor:pointer;text-decoration:underline">R${trick.round}</td>`;
      html += `<td>${leadSuitSym}${isDeclared ? '<span class="replay-declared">*</span>' : ''}</td>`;

      // Build card lookup by player index
      const cardByPlayer = {};
      trick.cards.forEach(([pidx, card]) => { cardByPlayer[pidx] = card; });

      playerOrder.forEach(pidx => {
        const card = cardByPlayer[pidx];
        if (!card) { html += '<td></td>'; return; }

        const isWinner = pidx === trick.winner;
        const isLead = pidx === trick.lead_player;
        const isSec = _isSecretaryCard(card, state);
        const display = card.is_joker
          ? (JOKER_DISPLAY[card.rank] || card.rank)
          : `${SUIT_SYM[card.suit] || ''}${card.rank}`;

        let cls = 'replay-card';
        if (isWinner) cls += ' replay-winner';
        if (isLead) cls += ' replay-lead';
        if (isSec) cls += ' replay-secretary';
        if (card.suit === 'hearts' || card.suit === 'diamonds') cls += ' replay-red';
        if (card.is_joker) cls += ' replay-joker';

        html += `<td class="${cls}">`;
        html += display;
        if (isSec) html += '<span class="replay-sec-badge">SEC</span>';
        if (isWinner) html += ' ★';
        html += '</td>';
      });

      // Points & running score
      const ptsDisplay = trick.points > 0 ? `+${trick.points}` : '-';
      html += `<td class="replay-pts">${ptsDisplay}</td>`;
      html += `<td class="replay-score">`;
      html += `<span class="replay-nap-score">N:${napRunning}</span> `;
      html += `<span class="replay-un-score">U:${unRunning}</span>`;
      if (justRevealed) html += ' <span class="replay-reveal-badge">📋</span>';
      html += `</td>`;
      html += '</tr>';
    });

    html += '</tbody></table></div>';
    return html;
  }

  function _renderInitialHands(replay, state) {
    let html = '';

    // Bidding history
    const bids = replay.bid_history || state.bid_history || [];
    if (bids.length > 0) {
      html += '<div class="swap-section"><h3>Bidding</h3>';
      html += '<div style="display:flex;flex-wrap:wrap;gap:0.4em;font-size:0.82rem">';
      bids.forEach(entry => {
        const p = state.players[entry.player];
        const name = p?.name || '?';
        if (entry.bid === 'pass') {
          html += `<span class="bid-tag pass">${name}: Pass</span>`;
        } else {
          html += `<span class="bid-tag bid">${name}: ${entry.bid}</span>`;
        }
      });
      html += '</div></div>';
    }

    // Bottom cards
    html += '<div class="swap-section"><h3>Bottom Cards (12)</h3>';
    html += `<div class="hand-stats">${_buildHandStats(replay.initial_bottom, state.trump_suit)}</div>`;
    html += '<div class="card-grid">';
    sortCards(replay.initial_bottom, state.trump_suit).forEach(c => { html += cardHTML(c); });
    html += '</div></div>';

    // Each player's hand
    for (let i = 0; i < 6; i++) {
      const p = state.players[i];
      const role = p.role === 'napoleon' ? ' 👑' : p.role === 'secretary' ? ' 📋' : ' 🌐';
      const cards = replay.initial_hands[i] || [];
      html += `<div class="swap-section"><h3>${p.name}${role}</h3>`;
      html += `<div class="hand-stats">${_buildHandStats(cards, state.trump_suit)}</div>`;
      html += '<div class="card-grid">';
      sortCards(cards, state.trump_suit).forEach(c => { html += cardHTML(c); });
      html += '</div></div>';
    }

    // Discarded cards
    if (replay.discarded_cards && replay.discarded_cards.length > 0) {
      const pts = replay.discarded_cards.filter(c => c.is_point).length;
      html += `<div class="swap-section"><h3>Discarded (${pts} point cards)</h3>`;
      html += '<div class="card-grid">';
      sortCards(replay.discarded_cards, state.trump_suit).forEach(c => { html += cardHTML(c); });
      html += '</div></div>';
    }
    return html;
  }

  function _renderStartingHands(replay, state) {
    const hands = replay.starting_hands || replay.initial_hands;
    let html = '';

    // Discarded cards
    if (replay.discarded_cards && replay.discarded_cards.length > 0) {
      const pts = replay.discarded_cards.filter(c => c.is_point).length;
      html += `<div class="swap-section"><h3>Discarded by Napoleon (${pts} point cards → UN)</h3>`;
      html += '<div class="card-grid">';
      sortCards(replay.discarded_cards, state.trump_suit).forEach(c => { html += cardHTML(c); });
      html += '</div></div>';
    }

    // Each player's actual playing hand
    for (let i = 0; i < 6; i++) {
      const p = state.players[i];
      const role = p.role === 'napoleon' ? ' 👑' : p.role === 'secretary' ? ' 📋' : ' 🌐';
      const cards = hands[i] || [];
      html += `<div class="swap-section"><h3>${p.name}${role} (${cards.length} cards)</h3>`;
      html += `<div class="hand-stats">${_buildHandStats(cards, state.trump_suit)}</div>`;
      html += '<div class="card-grid">';
      sortCards(cards, state.trump_suit).forEach(c => {
        const secAttr = _isSecretaryCard(c, state) ? 'data-secretary="true"' : '';
        html += cardHTML(c, secAttr);
      });
      html += '</div></div>';
    }
    return html;
  }

  // ================================================================
  // Strategy helpers
  // ================================================================
  function _analyzeHand(cards, trumpSuit) {
    const jokers = cards.filter(c => c.is_joker);
    const suits = {};
    const POINT_SET = new Set(['J','Q','K','A']);
    cards.forEach(c => {
      if (c.is_joker) return;
      if (!suits[c.suit]) suits[c.suit] = { cards: [], points: 0, aces: 0, kings: 0 };
      suits[c.suit].cards.push(c);
      if (POINT_SET.has(c.rank)) suits[c.suit].points++;
      if (c.rank === 'A') suits[c.suit].aces++;
      if (c.rank === 'K') suits[c.suit].kings++;
    });
    const sides = ['spades','hearts','diamonds','clubs'].filter(s => s !== trumpSuit);
    const trump = suits[trumpSuit] || { cards: [], points: 0, aces: 0, kings: 0 };
    const voids = sides.filter(s => !suits[s]);
    const shorts = sides.filter(s => suits[s] && suits[s].cards.length <= 2);
    const totalPts = cards.filter(c => !c.is_joker && POINT_SET.has(c.rank)).length;
    const allAces = cards.filter(c => !c.is_joker && c.rank === 'A');
    const sideAces = allAces.filter(c => c.suit !== trumpSuit);
    return { jokers, suits, trump, sides, voids, shorts, totalPts, allAces, sideAces };
  }

  function _cardLabel(c) {
    if (c.is_joker) return JOKER_DISPLAY[c.rank] || c.rank;
    return `${SUIT_SYM[c.suit]||''}${c.rank}`;
  }

  // ================================================================
  // Strategy Guide
  // ================================================================
  function _renderStrategyGuide(replay, state) {
    let html = '';
    const T = state.trump_suit;
    const Ts = SUIT_SYM[T]||'';
    const Tn = SUIT_NAMES[T]||'';
    const secCard = state.secretary_card;

    for (let pi = 0; pi < 6; pi++) {
      const p = state.players[pi];
      const role = p.role;
      const icon = role==='napoleon'?'👑':role==='secretary'?'📋':'🌐';
      const rn = role==='napoleon'?'Napoleon':role==='secretary'?'Secretary':'United Nations';
      const cards = (replay.starting_hands || replay.initial_hands)[pi] || [];
      const h = _analyzeHand(cards, T);
      const hasSec = cards.some(c => secCard && c.id === secCard.id);
      const bc = role==='napoleon'?'var(--clr-gold)':role==='secretary'?'#e67e22':'var(--clr-primary)';

      html += `<div class="swap-section" style="border-left:3px solid ${bc}">`;
      html += `<h3>${icon} ${p.name} — ${rn}</h3>`;
      html += `<div class="hand-stats">${_buildHandStats(cards, T)}</div>`;

      // --- Per-suit breakdown table ---
      html += '<table style="width:100%;font-size:0.78rem;margin:0.5em 0;border-collapse:collapse">';
      html += '<tr style="color:#aaa;border-bottom:1px solid rgba(255,255,255,0.1)"><td>Suit</td><td>Cards</td><td>Pts</td><td>Assessment</td></tr>';
      // Trump first
      const ts = h.trump;
      let tAssess = '';
      if (ts.cards.length >= 8) tAssess = 'Dominant — can flush all enemy trumps';
      else if (ts.cards.length >= 5) tAssess = 'Solid — lead A/K early, save low trumps for cutting';
      else if (ts.cards.length >= 2) tAssess = 'Thin — use only for cutting, avoid leading';
      else tAssess = 'Vulnerable — cannot control trump suit';
      html += `<tr><td style="color:var(--clr-gold)">${Ts} ${Tn}</td><td>${ts.cards.length}</td><td>${ts.points}</td><td style="color:#ddd">${tAssess}</td></tr>`;
      // Side suits
      for (const s of h.sides) {
        const si = h.suits[s];
        if (!si) {
          html += `<tr><td>${SUIT_SYM[s]} ${SUIT_NAMES[s]}</td><td>0</td><td>0</td><td style="color:var(--clr-success)">VOID — can cut with trump/joker every time</td></tr>`;
          continue;
        }
        let assess = '';
        if (si.aces > 0 && si.cards.length >= 3) assess = `Strong — lead A to grab ${si.points}pt, suit depth protects`;
        else if (si.aces > 0 && si.cards.length <= 2) assess = 'Lead A then void out — create cutting opportunity';
        else if (si.cards.length <= 2) assess = `Short (${si.cards.length}) — dump to create void quickly`;
        else if (si.kings > 0) assess = `K is risky (A may beat it) — feed K to ally if possible`;
        else assess = `No winners — dump low cards, feed points to ally`;
        html += `<tr><td>${SUIT_SYM[s]} ${SUIT_NAMES[s]}</td><td>${si.cards.length}</td><td>${si.points}</td><td style="color:#ddd">${assess}</td></tr>`;
      }
      html += '</table>';

      // --- Concrete play plan ---
      html += '<div style="font-size:0.82rem;color:#ccc;margin-top:0.5em">';
      html += '<div style="color:var(--clr-gold);font-weight:700;margin-bottom:0.3em">Play Plan:</div>';

      if (role === 'napoleon') {
        html += `<p>Contract: <strong>${state.contract_points}</strong>/48 pts needed.</p>`;
        // Lead order
        const leadOrder = [];
        if (h.sideAces.length) leadOrder.push(`Lead side Aces (${h.sideAces.map(_cardLabel).join(', ')}) — guaranteed ${h.sideAces.length}+ pts`);
        if (h.jokers.length && h.trump.cards.length < 8) leadOrder.push(`Use jokers to wash trump (declare ${Ts}) — force UN to spend trumps, then your trumps dominate`);
        if (h.trump.aces || h.trump.kings) leadOrder.push(`Lead ${Ts}A/${Ts}K to flush enemy trumps and collect points`);
        if (h.shorts.length) leadOrder.push(`Dump short suits (${h.shorts.map(s=>SUIT_SYM[s]+(h.suits[s]?.cards.length||0)).join(', ')}) to create voids for trump cuts`);
        if (h.jokers.length && h.trump.cards.length >= 8) leadOrder.push(`Use jokers to grab point-heavy tricks after trumps are exhausted`);
        leadOrder.push('Late game: cut any side suit with remaining trumps, feed J/Q/K to secretary');
        html += '<ol style="padding-left:1.2em;margin:0.3em 0;line-height:1.7">';
        leadOrder.forEach(s => html += `<li>${s}</li>`);
        html += '</ol>';
        // Risk
        const maxUNpts = 48 - state.contract_points;
        html += `<p style="color:var(--clr-danger)">UN can afford ${maxUNpts} pts. Every lost point-trick hurts. Prioritize winning tricks with 2+ point cards on table.</p>`;

      } else if (role === 'secretary') {
        html += `<p>You are <strong>undercover</strong>. All points you win transfer to Napoleon on reveal.</p>`;
        const plan = [];
        plan.push('Phase 1 (Undercover) — Win as many tricks as possible to accumulate points for Napoleon');
        if (h.allAces.length) plan.push(`Lead with Aces (${h.allAces.map(_cardLabel).join(', ')}) to grab points while appearing as UN`);
        if (h.voids.length) plan.push(`Void in ${h.voids.map(s=>SUIT_SYM[s]+SUIT_NAMES[s]).join(', ')} — cut enemy leads with trump to steal points`);
        if (h.totalPts >= 4) plan.push(`Feed J/Q/K (${h.totalPts - h.allAces.length} feedable pts) to Napoleon when he wins a trick`);
        if (hasSec) {
          plan.push(`Phase 2 (Reveal) — Play secretary card when 3+ point cards on table to capture maximum`);
          plan.push('After reveal: play aggressively like Napoleon, coordinate point feeding');
        }
        if (h.jokers.length) plan.push(`${h.jokers.length} joker(s): use to beat enemy jokers or secure critical point-heavy tricks`);
        html += '<ol style="padding-left:1.2em;margin:0.3em 0;line-height:1.7">';
        plan.forEach(s => html += `<li>${s}</li>`);
        html += '</ol>';
        html += `<p style="color:#e67e22">Timing is everything — reveal too early wastes surprise; too late wastes accumulated points.</p>`;

      } else {
        html += `<p>Goal: hold Napoleon below <strong>${state.contract_points}</strong> pts (UN needs ${48 - state.contract_points + 1}+ pts).</p>`;
        const plan = [];
        if (h.jokers.length) plan.push(`${h.jokers.length} joker(s): <strong>NEVER lead with jokers</strong>. Save as ambush — play when Napoleon/secretary is winning a trick with 2+ points`);
        if (h.trump.cards.length >= 4) plan.push(`Wash trump: lead ${Ts} to deplete Napoleon's trump supply (${h.trump.cards.length} trumps available)`);
        else if (h.trump.cards.length >= 1) plan.push(`${h.trump.cards.length} trump(s): save for cutting Napoleon's side-suit leads`);
        if (h.sideAces.length) plan.push(`Lead side Aces (${h.sideAces.map(_cardLabel).join(', ')}) to grab points for UN`);
        if (h.shorts.length) plan.push(`Short suits (${h.shorts.map(s=>SUIT_SYM[s]+(h.suits[s]?.cards.length||0)).join(', ')}): dump to create voids, then cut with trump/joker`);
        if (h.voids.length) plan.push(`Void in ${h.voids.map(s=>SUIT_SYM[s]+SUIT_NAMES[s]).join(', ')}: cut immediately when these suits are led`);
        const feedable = h.totalPts - h.allAces.length;
        if (feedable > 0) plan.push(`${feedable} feedable point card(s) (J/Q/K): dump to UN teammates when they're winning`);
        if (h.totalPts <= 2 && h.trump.cards.length <= 1) plan.push('Weak hand — play defensively, dump non-points, let strong UN teammates carry');
        plan.push('Watch for secretary reveal — once exposed, coordinate with UN to block both Napoleon and secretary');
        html += '<ol style="padding-left:1.2em;margin:0.3em 0;line-height:1.7">';
        plan.forEach(s => html += `<li>${s}</li>`);
        html += '</ol>';
      }
      html += '</div></div>';
    }
    return html;
  }

  // ================================================================
  // Per-Round Analysis
  // ================================================================
  function _renderRoundAnalysis(tricks, idx, replay, state) {
    const trick = tricks[idx];
    if (!trick) return '<p>No data</p>';
    const T = state.trump_suit;
    const Ts = SUIT_SYM[T]||'';

    // Reconstruct each player's hand at this round (from post-swap starting hands)
    const startHands = replay.starting_hands || replay.initial_hands;
    const hands = startHands.map(h => h.map(c => c.id));
    // Remove cards played in earlier rounds
    for (let r = 0; r < idx; r++) {
      tricks[r].cards.forEach(([pidx, card]) => {
        const i = hands[pidx].indexOf(card.id);
        if (i >= 0) hands[pidx].splice(i, 1);
      });
    }

    const leadSuitSym = SUIT_SYM[trick.lead_suit]||'';
    const leadSuitName = SUIT_NAMES[trick.lead_suit]||'';
    const leadCard = trick.cards[0]?.[1];
    const isDeclared = leadCard && (leadCard.is_joker || _isSecretaryCard(leadCard, state));
    const winnerName = state.players[trick.winner]?.name||'?';

    let html = '';
    // Header
    html += `<div style="text-align:center;margin-bottom:0.8em">`;
    html += `<span style="font-size:1.2rem;font-weight:700;color:var(--clr-gold)">Round ${trick.round}</span>`;
    html += `<span style="margin-left:1em">Lead: ${state.players[trick.lead_player]?.name}</span>`;
    html += `<span style="margin-left:1em">Suit: <span style="font-size:1.2em">${leadSuitSym}</span> ${leadSuitName}</span>`;
    if (isDeclared) html += `<span style="margin-left:0.5em;color:#faa">(declared)</span>`;
    html += `<span style="margin-left:1em;color:var(--clr-gold)">Winner: ${winnerName} ★</span>`;
    html += `<span style="margin-left:0.5em">+${trick.points}pt</span>`;
    html += `</div>`;

    // Running score (with secretary transfer logic)
    const discPts = (replay.discarded_cards || []).filter(c => c.is_point).length;
    let napPts = 0, unPts = discPts, secAcc = 0;
    let secRev = false;
    for (let r = 0; r <= idx; r++) {
      const t = tricks[r];
      const wp = state.players[t.winner];
      const jr = t.secretary_revealed && !secRev;
      secRev = t.secretary_revealed || secRev;
      if (jr) { napPts += secAcc; unPts -= secAcc; }
      const isNap = wp?.role === 'napoleon' || (wp?.role === 'secretary' && secRev);
      if (isNap) { napPts += t.points; }
      else { unPts += t.points; if (wp?.role === 'secretary' && !secRev) secAcc += t.points; }
    }
    html += `<div style="text-align:center;font-size:0.85rem;margin-bottom:1em;color:#aaa">Score after this round: <span style="color:var(--clr-gold)">N:${napPts}</span> / <span style="color:var(--clr-primary)">U:${unPts}</span></div>`;

    // Per-player analysis table
    html += '<table style="width:100%;font-size:0.8rem;border-collapse:collapse">';
    html += '<tr style="border-bottom:1px solid rgba(255,255,255,0.15);color:#aaa"><td style="width:15%">Player</td><td style="width:15%">Played</td><td style="width:10%">Role</td><td>Analysis</td></tr>';

    // Build card lookup and play order
    const playOrder = trick.cards.map(([pidx]) => pidx);

    trick.cards.forEach(([pidx, card], playIdx) => {
      const p = state.players[pidx];
      const isWinner = pidx === trick.winner;
      const isLead = pidx === trick.lead_player;
      const role = p.role;
      const icon = role==='napoleon'?'👑':role==='secretary'?'📋':'🌐';
      const isSec = _isSecretaryCard(card, state);
      const cardDisp = _cardLabel(card) + (isSec ? ' <span style="color:#e67e22">SEC</span>' : '');
      const winMark = isWinner ? ' <span style="color:var(--clr-gold)">★</span>' : '';
      const leadMark = isLead ? ' <span style="color:#888;font-size:0.7em">(lead)</span>' : '';

      // Analyze the play
      const handBefore = hands[pidx];
      const analysis = _analyzePlay(pidx, card, trick, playIdx, handBefore, replay, state, T);

      const rowBg = playIdx % 2 === 0 ? 'rgba(255,255,255,0.03)' : 'transparent';
      html += `<tr style="background:${rowBg};border-bottom:1px solid rgba(255,255,255,0.05)">`;
      html += `<td style="font-weight:600">${p.name}${leadMark}</td>`;
      html += `<td>${cardDisp}${winMark}</td>`;
      html += `<td>${icon}</td>`;
      html += `<td style="color:#ccc">${analysis}</td>`;
      html += '</tr>';
    });
    html += '</table>';

    if (trick.secretary_revealed) {
      const prevRevealed = idx > 0 && tricks[idx-1].secretary_revealed;
      if (!prevRevealed) {
        html += `<div style="text-align:center;margin-top:0.8em;color:#e67e22;font-weight:700">📋 Secretary revealed this round! Points transferred to Napoleon.</div>`;
      }
    }
    return html;
  }

  function _analyzePlay(pidx, card, trick, playIdx, handIds, replay, state, trumpSuit) {
    const role = state.players[pidx].role;
    const isLead = pidx === trick.lead_player;
    const isWinner = pidx === trick.winner;
    const leadSuit = trick.lead_suit;
    const isSec = _isSecretaryCard(card, state);

    // Get all initial cards to look up by ID
    const allInitial = replay.initial_hands.flat();
    const handCards = handIds.map(id => allInitial.find(c => c.id === id)).filter(Boolean);
    const hasLeadSuit = handCards.some(c => !c.is_joker && c.suit === leadSuit);
    const trickPts = trick.points;

    // Count points on table before this player (from cards played before this index)
    let ptsBefore = 0;
    for (let i = 0; i < playIdx; i++) {
      const c = trick.cards[i][1];
      if (!c.is_joker && ['J','Q','K','A'].includes(c.rank)) ptsBefore++;
    }

    const parts = [];

    if (isLead) {
      if (card.is_joker) {
        parts.push(`Led with joker (declared ${SUIT_SYM[leadSuit]}${SUIT_NAMES[leadSuit]})`);
        if (leadSuit === trumpSuit) parts.push('— washing trump: forces all to play trumps');
        else parts.push('— grabbing points with guaranteed winner');
      } else if (isSec) {
        parts.push(`Led with secretary card! Revealed identity`);
      } else if (card.rank === 'A') {
        parts.push(`Led ${SUIT_SYM[card.suit]}A — near-guaranteed winner, collects points from followers`);
      } else if (card.suit === trumpSuit) {
        parts.push(`Led trump ${_cardLabel(card)} — flushing enemy trumps`);
        if (['3','6','9'].includes(card.rank) && trick.round >= 2 && trick.round <= 5)
          parts.push('+ call-joker trigger!');
      } else {
        parts.push(`Led ${_cardLabel(card)}`);
        if (card.rank === 'K') parts.push('— risky, Ace could beat it');
        else if (['J','Q'].includes(card.rank)) parts.push('— weak lead, likely to lose');
        else parts.push('— low card, probing or dumping');
      }
    } else {
      // Following
      if (!hasLeadSuit && !card.is_joker && !isSec) {
        // Void in lead suit
        if (card.suit === trumpSuit) {
          parts.push(`Cut with trump ${_cardLabel(card)} (void in ${SUIT_SYM[leadSuit]})`);
          if (ptsBefore >= 2) parts.push(`— good: ${ptsBefore}pts on table worth stealing`);
          else parts.push('— aggressive cut to take control');
          // Check: should have used a lower trump?
          const myTrumps = handCards.filter(c => !c.is_joker && c.suit === trumpSuit);
          const lowerTrumps = myTrumps.filter(c => RANK_ORDER[c.rank] < RANK_ORDER[card.rank]);
          if (lowerTrumps.length > 0 && isWinner)
            parts.push(`<span style="color:var(--clr-success)">Tip: could save big trump, use ${_cardLabel(lowerTrumps[0])} instead</span>`);
        } else {
          parts.push(`Dumped ${_cardLabel(card)} (void in ${SUIT_SYM[leadSuit]})`);
          if (card.is_point) parts.push(`<span style="color:var(--clr-danger)">Wasted ${card.rank} point — should feed to ally instead?</span>`);
          else parts.push('— discarding non-point, correct');
        }
      } else if (card.is_joker) {
        if (ptsBefore >= 2) parts.push(`Joker ambush on ${ptsBefore}pts — excellent timing`);
        else if (ptsBefore >= 1) parts.push(`Joker used for ${ptsBefore}pt — acceptable`);
        else parts.push(`Joker on 0pts — wasteful, better saved for high-value trick`);
      } else if (isSec) {
        parts.push(`Secretary card played! ${ptsBefore}pts captured`);
        if (ptsBefore >= 3) parts.push('— great timing, maximum capture');
        else if (ptsBefore >= 1) parts.push('— okay timing');
        else parts.push(`<span style="color:var(--clr-danger)">— poor timing, no points to capture</span>`);
      } else {
        // Normal follow
        if (isWinner) {
          parts.push(`Won with ${_cardLabel(card)}`);
          if (trickPts >= 3) parts.push('— great, captured high-value trick');
        } else {
          const isAllyWinning = _isAlly(pidx, trick.winner, state);
          if (isAllyWinning && card.is_point && card.rank !== 'A') {
            parts.push(`Fed ${_cardLabel(card)} to ally — correct, maximizing ally's haul`);
          } else if (isAllyWinning && card.is_point && card.rank === 'A') {
            parts.push(`Fed ${_cardLabel(card)} to ally`);
            const suitDepth = handCards.filter(c => !c.is_joker && c.suit === card.suit).length;
            if (suitDepth <= 1) parts.push('— lone A, correct to feed');
            else parts.push(`<span style="color:var(--clr-danger)">— had ${suitDepth} cards in suit, could lead A yourself to win a trick</span>`);
          } else if (isAllyWinning) {
            parts.push(`Played ${_cardLabel(card)} — ally winning, low dump OK`);
            // Check: had feedable points?
            const feedable = handCards.filter(c => !c.is_joker && ['J','Q','K'].includes(c.rank) && c.suit === leadSuit);
            if (feedable.length > 0) parts.push(`<span style="color:var(--clr-danger)">Tip: could feed ${feedable.map(_cardLabel).join('/')} to ally</span>`);
          } else {
            parts.push(`Played ${_cardLabel(card)}`);
            if (card.is_point) parts.push(`<span style="color:var(--clr-danger)">— lost point to enemy!</span>`);
            else parts.push('— couldn\'t win, dumped low');
          }
        }
      }
    }
    return parts.join(' ');
  }

  function _isAlly(myIdx, winnerIdx, state) {
    const myRole = state.players[myIdx]?.role;
    const winRole = state.players[winnerIdx]?.role;
    const napTeam = ['napoleon','secretary'];
    if (napTeam.includes(myRole) && napTeam.includes(winRole)) return true;
    if (!napTeam.includes(myRole) && !napTeam.includes(winRole)) return true;
    return false;
  }

  // ================================================================
  // Screen management
  // ================================================================
  function showScreen(id) {
    $$('.screen').forEach(s => s.classList.remove('active'));
    $(`#${id}`).classList.add('active');
  }

  return {
    updateInfoBar, updateSeats, updateTrickArea, renderHand,
    setActionBar, clearActionBar, renderBiddingActions, renderBidHistory,
    showModal, hideModal, showTrumpChooser, showSwapUI, showSecretaryChooser,
    showAnnouncement, showLeadSuitChooser, showCallJokerChooser, showGameOver, showReplay, showScreen, cardHTML,
  };
})();

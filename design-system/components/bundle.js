/* @ds-bundle: {"format":4,"namespace":"MiraVoice","components":[{"name":"Button"},{"name":"StatusPill"},{"name":"CallPanel"},{"name":"DialPad"},{"name":"KpiTile"},{"name":"TextField"}]} */
(function () {
  var R = window.React, h = R.createElement;
  function cx() { return Array.prototype.filter.call(arguments, Boolean).join(' '); }
  function omit(o, keys) { var r = {}; for (var k in o) { if (keys.indexOf(k) < 0) r[k] = o[k]; } return r; }

  /* ---------- icons: 24px grid, 1.75 stroke, round caps ---------- */
  var PATHS = {
    phone: 'M5 4h3l2 5-2.5 1.5a11 11 0 0 0 6 6L15 14l5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2',
    mic: 'M12 3a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3M5 11a7 7 0 0 0 14 0M12 18v3',
    micOff: 'M3 3l18 18M9 9v2a3 3 0 0 0 5 2.2M15 9.3V6a3 3 0 0 0-5.7-1.3M5 11a7 7 0 0 0 11.5 5.4M19 11a7 7 0 0 1-.6 2.8M12 18v3',
    pause: 'M8 5v14M16 5v14',
    transfer: 'M4 8h13l-3-3M20 16H7l3 3',
    keypad: 'M6 5h.01M12 5h.01M18 5h.01M6 11h.01M12 11h.01M18 11h.01M6 17h.01M12 17h.01M18 17h.01',
    record: 'M12 7a5 5 0 1 1 0 10a5 5 0 0 1 0-10',
    back: 'M20 12H6M11 6l-6 6 6 6',
    trendUp: 'M4 16l6-6 4 4 6-6M14 8h6v6',
    trendDown: 'M4 8l6 6 4-4 6 6M14 16h6v-6',
    alert: 'M12 8v5M12 16.5h.01M10.3 4.2L2.8 17.5A2 2 0 0 0 4.5 20.5h15a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0'
  };
  function Icon(props) {
    var size = props.size || 20;
    return h('svg', { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: props.weight || 1.75, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true, className: props.className, style: props.style },
      h('path', { d: PATHS[props.name] }));
  }

  /* ---------- Button ---------- */
  function Button(props) {
    var v = props.variant || 'primary', s = props.size || 'md';
    var rest = omit(props, ['variant', 'size', 'icon', 'className', 'children']);
    return h('button', Object.assign({ type: 'button' }, rest, { className: cx('mv-btn', 'mv-btn--' + v, 'mv-btn--' + s, props.className) }),
      props.icon ? h(Icon, { name: props.icon, size: s === 'sm' ? 16 : 20 }) : null,
      props.children ? h('span', null, props.children) : null);
  }

  /* ---------- StatusPill ---------- */
  var STATUS = {
    available: { tone: 'live', en: 'Available', ar: 'متاح', fr: 'Disponible' },
    ringing: { tone: 'ringing', en: 'Ringing', ar: 'يرن', fr: 'Sonnerie' },
    'on-call': { tone: 'active', en: 'On call', ar: 'في مكالمة', fr: 'En appel' },
    hold: { tone: 'hold', en: 'On hold', ar: 'قيد الانتظار', fr: 'En attente' },
    'wrap-up': { tone: 'hold', en: 'Wrap-up', ar: 'إنهاء المكالمة', fr: 'Post-appel' },
    'break': { tone: 'offline', en: 'Break', ar: 'استراحة', fr: 'Pause' },
    offline: { tone: 'offline', en: 'Offline', ar: 'غير متصل', fr: 'Hors ligne' }
  };
  function StatusPill(props) {
    var st = STATUS[props.status] || STATUS.offline, lang = props.lang || 'en';
    return h('span', { className: cx('mv-pill', 'mv-pill--' + st.tone, props.className), role: 'status' },
      h('span', { className: 'mv-pill__dot', 'aria-hidden': true }),
      h('span', { className: 'mv-pill__label' }, props.label || st[lang] || st.en),
      props.timer ? h('span', { className: 'mv-pill__timer' }, props.timer) : null);
  }

  /* ---------- CallPanel ---------- */
  function Control(p) {
    return h('button', { type: 'button', className: cx('mv-ctrl', p.on && 'is-on'), 'aria-pressed': p.on ? 'true' : 'false', onClick: p.onClick },
      h(Icon, { name: p.icon, size: 22 }), h('span', { className: 'mv-ctrl__label' }, p.label));
  }
  function CallPanel(props) {
    var state = props.state || 'connected';
    var _m = R.useState(false), muted = _m[0], setMuted = _m[1];
    var _h = R.useState(state === 'hold'), held = _h[0], setHeld = _h[1];
    var shown = held ? 'hold' : state;
    var title = { ringing: 'Incoming call', connected: 'On call', hold: 'On hold' }[shown];
    var fields = props.fields || [];
    return h('section', { className: cx('mv-call', 'mv-call--' + shown, props.className), 'aria-label': title + ' — ' + props.callerName },
      h('header', { className: 'mv-call__bar' },
        h('span', { className: 'mv-call__state' }, title),
        props.queue ? h('span', { className: 'mv-call__queue' }, props.queue) : null,
        h('span', { className: 'mv-call__timer' }, props.timer || '00:00')),
      h('div', { className: 'mv-call__who' },
        h('div', { className: 'mv-call__name' }, props.callerName || 'Unknown caller'),
        h('div', { className: 'mv-call__number', dir: 'ltr' }, props.number)),
      fields.length ? h('dl', { className: 'mv-call__card' }, fields.map(function (f, i) {
        return h('div', { key: i, className: 'mv-call__field' }, h('dt', null, f.label), h('dd', null, f.value));
      })) : null,
      shown === 'ringing'
        ? h('div', { className: 'mv-call__answer' },
            h('button', { type: 'button', className: 'mv-round mv-round--decline', 'aria-label': 'Decline', onClick: props.onDecline }, h(Icon, { name: 'phone', size: 26, style: { transform: 'rotate(135deg)' } })),
            h('button', { type: 'button', className: 'mv-round mv-round--answer', 'aria-label': 'Answer', onClick: props.onAnswer }, h(Icon, { name: 'phone', size: 26 })))
        : h('div', { className: 'mv-call__controls' },
            h('div', { className: 'mv-call__grid' },
              h(Control, { icon: muted ? 'micOff' : 'mic', label: muted ? 'Unmute' : 'Mute', on: muted, onClick: function () { setMuted(!muted); } }),
              h(Control, { icon: 'pause', label: held ? 'Resume' : 'Hold', on: held, onClick: function () { setHeld(!held); } }),
              h(Control, { icon: 'transfer', label: 'Transfer', onClick: props.onTransfer }),
              h(Control, { icon: 'keypad', label: 'Keypad', onClick: props.onKeypad })),
            h('button', { type: 'button', className: 'mv-round mv-round--hangup', 'aria-label': 'Hang up', onClick: props.onHangup }, h(Icon, { name: 'phone', size: 26, style: { transform: 'rotate(135deg)' } }))));
  }

  /* ---------- DialPad ---------- */
  var KEYS = [['1', ''], ['2', 'ABC'], ['3', 'DEF'], ['4', 'GHI'], ['5', 'JKL'], ['6', 'MNO'], ['7', 'PQRS'], ['8', 'TUV'], ['9', 'WXYZ'], ['*', ''], ['0', '+'], ['#', '']];
  function DialPad(props) {
    var _v = R.useState(props.defaultValue || ''), val = _v[0], setVal = _v[1];
    function press(k) { var n = val + k; setVal(n); if (props.onChange) props.onChange(n); }
    return h('div', { className: cx('mv-dial', props.className) },
      h('div', { className: 'mv-dial__display', dir: 'ltr', 'aria-live': 'polite' },
        h('span', { className: 'mv-dial__value' }, val || h('span', { className: 'mv-dial__hint' }, props.placeholder || 'Enter a number')),
        val ? h('button', { type: 'button', className: 'mv-dial__del', 'aria-label': 'Delete digit', onClick: function () { setVal(val.slice(0, -1)); } }, h(Icon, { name: 'back', size: 20 })) : null),
      h('div', { className: 'mv-dial__keys', dir: 'ltr' }, KEYS.map(function (k) {
        return h('button', { key: k[0], type: 'button', className: 'mv-dial__key', onClick: function () { press(k[0]); }, 'aria-label': k[0] },
          h('span', { className: 'mv-dial__digit' }, k[0]), h('span', { className: 'mv-dial__letters' }, k[1] || ' '));
      })),
      h('button', { type: 'button', className: 'mv-round mv-round--answer mv-dial__call', 'aria-label': 'Call', disabled: !val, onClick: function () { if (props.onCall) props.onCall(val); } }, h(Icon, { name: 'phone', size: 26 })));
  }

  /* ---------- KpiTile ---------- */
  function KpiTile(props) {
    var status = props.status || 'ok', size = props.size || 'md';
    var word = { ok: 'On target', warn: 'At risk', bad: 'Below target' }[status];
    return h('div', { className: cx('mv-kpi', 'mv-kpi--' + status, 'mv-kpi--' + size, props.className) },
      h('div', { className: 'mv-kpi__label' }, props.label),
      h('div', { className: 'mv-kpi__value' }, props.value, props.unit ? h('span', { className: 'mv-kpi__unit' }, props.unit) : null),
      h('div', { className: 'mv-kpi__foot' },
        h('span', { className: 'mv-kpi__status' }, h('span', { className: 'mv-kpi__dot', 'aria-hidden': true }), word),
        props.target ? h('span', { className: 'mv-kpi__target' }, 'Target ' + props.target) : null,
        props.trend ? h('span', { className: 'mv-kpi__trend' }, h(Icon, { name: props.trend.charAt(0) === '-' ? 'trendDown' : 'trendUp', size: 16 }), props.trend) : null));
  }

  /* ---------- TextField ---------- */
  var uid = 0;
  function TextField(props) {
    var idRef = R.useRef(null); if (!idRef.current) idRef.current = 'mv-f-' + (++uid);
    var id = props.id || idRef.current, hint = id + '-hint';
    var rest = omit(props, ['label', 'hint', 'error', 'className', 'id', 'mono']);
    return h('div', { className: cx('mv-field', props.error && 'is-error', props.className) },
      h('label', { className: 'mv-field__label', htmlFor: id }, props.label),
      h('input', Object.assign({ id: id, className: cx('mv-field__input', props.mono && 'is-mono'), 'aria-invalid': props.error ? 'true' : undefined, 'aria-describedby': (props.error || props.hint) ? hint : undefined }, rest)),
      props.error
        ? h('div', { id: hint, className: 'mv-field__error' }, h(Icon, { name: 'alert', size: 16 }), props.error)
        : props.hint ? h('div', { id: hint, className: 'mv-field__hint' }, props.hint) : null);
  }

  var api = { Button: Button, StatusPill: StatusPill, CallPanel: CallPanel, DialPad: DialPad, KpiTile: KpiTile, TextField: TextField, Icon: Icon };
  window.MiraVoice = Object.assign(window.MiraVoice || {}, api);
})();

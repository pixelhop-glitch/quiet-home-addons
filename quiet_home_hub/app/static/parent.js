// Parent app for the Quiet Home hub. Paths are relative so it works behind Home Assistant ingress.
(function () {
  'use strict';
  var periods = {any: 'Any time', day: 'Day', night: 'Night'};
  var uploadPeriod = 'any', filter = 'all', photos = [];
  function $(id) { return document.getElementById(id); }
  function el(tag, className, text) { var n = document.createElement(tag); if (className) n.className = className; if (text != null) n.textContent = text; return n; }
  function api(path, options) {
    return fetch(path, options).then(function (r) {
      return r.json().then(function (data) { if (!r.ok) throw new Error(data.error || r.statusText); return data; });
    });
  }
  function post(path, data) { return api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)}); }

  // Tabs
  document.querySelectorAll('nav button').forEach(function (tab) {
    tab.onclick = function () {
      document.querySelectorAll('nav button').forEach(function (t) { t.setAttribute('aria-selected', t === tab); });
      document.querySelectorAll('.tab').forEach(function (s) { s.hidden = s.id !== tab.dataset.tab; });
      if (tab.dataset.tab === 'tv') loadStatus();
    };
  });

  // Photos
  document.querySelectorAll('#upload-period button').forEach(function (b) {
    b.onclick = function () { uploadPeriod = b.dataset.period; document.querySelectorAll('#upload-period button').forEach(function (x) { x.classList.toggle('on', x === b); }); };
  });
  $('upload-files').onchange = function () {
    var files = Array.prototype.slice.call(this.files), caption = $('upload-caption').value.trim(), done = 0, failed = 0, input = this;
    if (!files.length) return;
    function next() {
      if (!files.length) {
        $('upload-status').textContent = failed ? done + ' added, ' + failed + ' could not be read.' : done + (done === 1 ? ' photo' : ' photos') + ' added.';
        input.value = ''; loadPhotos(); return;
      }
      var file = files.shift();
      $('upload-status').textContent = 'Uploading ' + (done + failed + 1) + '…';
      api('api/photos?' + new URLSearchParams({period: uploadPeriod, caption: caption}), {method: 'PUT', body: file})
        .then(function () { done++; }, function () { failed++; }).then(next);
    }
    next();
  };
  function renderFilters() {
    var bar = $('filters'); bar.textContent = '';
    ['all', 'any', 'day', 'night'].forEach(function (key) {
      var count = key === 'all' ? photos.length : photos.filter(function (p) { return p.period === key; }).length;
      var b = el('button', key === filter ? 'on' : '', (key === 'all' ? 'All' : periods[key]) + ' · ' + count);
      b.onclick = function () { filter = key; render(); };
      bar.appendChild(b);
    });
  }
  function render() {
    renderFilters();
    var grid = $('grid'), shown = photos.filter(function (p) { return filter === 'all' || p.period === filter; });
    grid.textContent = ''; $('empty').hidden = photos.length > 0;
    shown.forEach(function (photo) {
      var card = el('div', 'photo'), img = el('img'), meta = el('div', 'meta'), caption = el('input'), row = el('div', 'row'), period = el('select'), remove = el('button', 'delete', 'Delete');
      img.src = 'thumbs/' + photo.id; img.alt = photo.caption || 'Photo'; img.loading = 'lazy';
      caption.value = photo.caption; caption.placeholder = 'Add a caption'; caption.maxLength = 120;
      caption.onchange = function () { post('api/photos/update', {id: photo.id, caption: caption.value.trim()}).then(loadPhotos); };
      Object.keys(periods).forEach(function (key) { var o = el('option', '', periods[key]); o.value = key; o.selected = key === photo.period; period.appendChild(o); });
      period.onchange = function () { post('api/photos/update', {id: photo.id, period: period.value}).then(loadPhotos); };
      remove.onclick = function () { if (confirm('Delete this photo from the TV?')) post('api/photos/delete', {id: photo.id}).then(loadPhotos); };
      row.appendChild(period); row.appendChild(remove); meta.appendChild(caption); meta.appendChild(row);
      card.appendChild(img); card.appendChild(meta); grid.appendChild(card);
    });
  }
  function loadPhotos() { api('api/photos').then(function (list) { photos = list; render(); }); }

  // Family notes
  function noteRow(note) {
    var row = el('div', 'note-row'), value = el('input'), label = el('input');
    value.placeholder = 'Bins'; value.maxLength = 24; value.value = note.value || '';
    label.placeholder = 'Recycling tomorrow'; label.maxLength = 40; label.value = note.label || '';
    row.appendChild(value); row.appendChild(label); return row;
  }
  function loadNotes() {
    api('api/notes').then(function (notes) {
      $('notes-title').value = notes.title || ''; $('notes-rows').textContent = '';
      for (var i = 0; i < 3; i++) $('notes-rows').appendChild(noteRow(notes.items[i] || {}));
    });
  }
  $('notes-save').onclick = function () {
    var items = Array.prototype.map.call(document.querySelectorAll('.note-row'), function (row) {
      var inputs = row.querySelectorAll('input'); return {value: inputs[0].value.trim(), label: inputs[1].value.trim()};
    }).filter(function (n) { return n.value || n.label; });
    post('api/notes', {title: $('notes-title').value.trim(), items: items}).then(function () { $('notes-status').textContent = 'Saved. The TV picks this up within a minute.'; });
  };

  // TV status
  function loadStatus() {
    api('api/status').then(function (status) {
      var list = $('checks'); list.textContent = '';
      if (!status.entities.length) list.appendChild(el('li', '', 'Nothing chosen yet.'));
      status.entities.forEach(function (check) {
        var li = el('li'), name = el('span'); name.appendChild(document.createTextNode(check.label + ' ')); name.appendChild(el('code', '', check.entity));
        li.appendChild(name); li.appendChild(el('span', check.found ? 'ok' : 'missing', check.found ? 'Found' : 'Not found')); list.appendChild(li);
      });
      $('tv-port').textContent = status.tvPort;
      $('key-status').textContent = status.keySet ? 'A TV key is set, so only the TV can read the dashboard.' : 'No TV key is set. Add one in Configuration so only the TV can read the dashboard.';
    });
  }

  loadPhotos(); loadNotes();
})();

'use strict';

import 'whatwg-fetch';
import { dataURL, ActivateMessageBoard, micboard, updateNavLinks } from './app.js';
import { renderGroup, updateSlot } from './channelview.js';
import { updateChart } from './chart-smoothie.js';


export function postJSON(url, data, callback) {
  fetch(url, {
    method: 'POST',
    body: JSON.stringify(data),
    headers: {
      'Content-Type': 'application/json',
    },
  }).then(res => res.json())
    .then((response) => {
      console.log('Success:', JSON.stringify(response))
      if (callback) {
        callback();
      }
    })
    .catch(error => console.error('Error:', error));
}

function JsonUpdate() {
  fetch(dataURL)
    .then(response => response.json())
    .then((data) => {
      if (micboard.connectionStatus === 'DISCONNECTED') {
        window.location.reload();
      }
      data.receivers.forEach((rx) => {
        rx.tx.forEach(updateSlot);
      });
      micboard.connectionStatus = 'CONNECTED';
      micboard.config = data.config;
    }).catch((error) => {
      console.log(error);
      micboard.connectionStatus = 'DISCONNECTED';
    });
}


function updateGroup(data) {
  const group = parseInt(data.group, 10);
  console.log('dgroup: ' + group + ' mgroup: ' + micboard.group);
  if (!micboard.groups[group]) {
    micboard.groups[group] = {};
  }
  micboard.groups[group].title = data.title;
  micboard.groups[group].slots = data.slots;
  micboard.groups[group].hide_charts = data.hide_charts === true;
  if (micboard.group === group) {
    renderGroup(group);
  }
  updateNavLinks();
}

export function initLiveData() {
  setInterval(JsonUpdate, 1000);
  wsConnect();
}

function wsConnect() {
  const loc = window.location;
  let newUri;

  if (loc.protocol === 'https:') {
    newUri = 'wss:';
  } else {
    newUri = 'ws:';
  }

  newUri += '//' + loc.host + loc.pathname + 'ws';

  micboard.socket = new WebSocket(newUri);

  micboard.socket.onmessage = (msg) => {
    const data = JSON.parse(msg.data);

    if (data['chart-update']) {
      data['chart-update'].forEach(updateChart);
    }
    if (data['data-update']) {
      data['data-update'].forEach(updateSlot);
    }

    if (data['group-update']) {
      data['group-update'].forEach(updateGroup);
      updateNavLinks();
    }
  };

  micboard.socket.onclose = () => {
    ActivateMessageBoard();
  };

  micboard.socket.onerror = () => {
    ActivateMessageBoard();
  };
}

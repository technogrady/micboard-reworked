'use strict';

import { micboard, updateHash, generateQR } from './app.js';
import { toggleInfoDrawer, toggleImageBackground, toggleVideoBackground, toggleDisplayMode } from './display';
import { renderGroup } from './channelview.js';
import { groupEditToggle } from './dnd.js';
import { slotEditToggle } from './extended.js';
import { initConfigEditor } from './config.js';


// https://developer.mozilla.org/en-US/docs/Web/API/Fullscreen_API
function toggleFullScreen() {
  const el = document.documentElement;
  if (!document.fullscreenElement && !document.webkitFullscreenElement) {
    if (el.requestFullscreen) {
      el.requestFullscreen();
    } else if (el.webkitRequestFullscreen) {
      el.webkitRequestFullscreen();
    }
  } else if (document.exitFullscreen) {
    document.exitFullscreen();
  } else if (document.webkitExitFullscreen) {
    document.webkitExitFullscreen();
  }
}

function uiLocked() {
  return $('.settings').is(':visible')
    || $('.editzone').is(':visible')
    || $('.sidebar-nav').is(':visible');
}

function reloadPage() {
  micboard.settingsMode = 'NONE';
  updateHash();
  window.location.reload();
}

// every keyboard shortcut as a named action, shared by keys and toolbar buttons
const shortcutActions = {
  demo: () => {
    micboard.url.demo = !micboard.url.demo;
    updateHash();
    window.location.reload();
  },
  groupEdit: () => {
    if (micboard.group !== 0) {
      groupEditToggle();
    }
  },
  fullscreen: toggleFullScreen,
  imageBackground: toggleImageBackground,
  infoDrawer: toggleInfoDrawer,
  nameEdit: slotEditToggle,
  bulkNameEdit: () => {
    slotEditToggle();
    $('#paste-box').show();
  },
  configEdit: initConfigEditor,
  qr: () => {
    generateQR();
    $('.modal').modal('toggle');
  },
  tvMode: toggleDisplayMode,
  videoBackground: toggleVideoBackground,
  help: () => {
    $('#hud').toggle();
  },
  reload: reloadPage,
};

// the background toggles only apply in TV view, so their buttons enter it first
const buttonActions = Object.assign({}, shortcutActions, {
  imageBackground: () => {
    if (micboard.displayMode !== 'tvmode') {
      toggleDisplayMode();
    }
    toggleImageBackground();
  },
  videoBackground: () => {
    if (micboard.displayMode !== 'tvmode') {
      toggleDisplayMode();
    }
    toggleVideoBackground();
  },
});

const keymap = {
  d: 'demo',
  e: 'groupEdit',
  f: 'fullscreen',
  g: 'imageBackground',
  i: 'infoDrawer',
  n: 'nameEdit',
  N: 'bulkNameEdit',
  s: 'configEdit',
  q: 'qr',
  t: 'tvMode',
  v: 'videoBackground',
  '?': 'help',
};

const TOOLBAR_PREF_KEY = 'micboard-toolbar';

function initToolbar() {
  const container = document.getElementById('container');

  $('#toolbar').on('click', 'button[data-group]', (e) => {
    if (uiLocked()) {
      return;
    }
    renderGroup(parseInt(e.currentTarget.getAttribute('data-group'), 10));
  });

  $('#toolbar').on('click', 'button[data-action]', (e) => {
    const action = e.currentTarget.getAttribute('data-action');
    if (action !== 'reload' && uiLocked()) {
      return;
    }
    buttonActions[action]();
  });

  if (localStorage.getItem(TOOLBAR_PREF_KEY) === 'hidden') {
    container.classList.add('toolbar-hidden');
  }

  $('#toolbar-toggle').click(() => {
    container.classList.toggle('toolbar-hidden');
    localStorage.setItem(TOOLBAR_PREF_KEY, container.classList.contains('toolbar-hidden') ? 'hidden' : 'shown');
  });

  // hide the whole navbar while fullscreen; the faint corner button brings it back
  const fullscreenChange = () => {
    const active = !!(document.fullscreenElement || document.webkitFullscreenElement);
    container.classList.toggle('fullscreen-active', active);
    container.classList.remove('shownav');
  };
  document.addEventListener('fullscreenchange', fullscreenChange);
  document.addEventListener('webkitfullscreenchange', fullscreenChange);

  $('#nav-reveal').click(() => {
    container.classList.toggle('shownav');
  });
}

export function keybindings() {
  $('#hud-button').click(() => {
    $('#hud').hide();
  });

  initToolbar();

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      reloadPage();
    }
    if (uiLocked()) {
      return;
    }

    if (e.key >= '0' && e.key <= '9') {
      renderGroup(parseInt(e.key, 10));
      return;
    }

    const action = keymap[e.key];
    if (action) {
      shortcutActions[action]();
    }
  }, false);
}

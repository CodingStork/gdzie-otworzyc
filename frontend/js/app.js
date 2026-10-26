// Punkt startowy frontendu: spina mapę z panelem bocznym.
import { initMap } from './map.js';

const $ = (id) => document.getElementById(id);
const view = initMap('map');
const state = { lat: null, lng: null };

function radiusKm() { return Number($('radius-input').value); }

function redrawArea() {
  if (state.lat == null) return;
  view.setPin(state.lat, state.lng);
  view.setAreaCircle(state.lat, state.lng, $('poland-checkbox').checked ? null : radiusKm());
}

view.onClick((lat, lng) => { state.lat = lat; state.lng = lng; redrawArea(); });
$('radius-input').addEventListener('input', () => {
  $('radius-value').textContent = radiusKm();
  redrawArea();
});

// Mobile: uchwyt zwija i rozwija arkusz.
$('sheet-handle').addEventListener('click', () => $('sidebar').classList.toggle('collapsed'));

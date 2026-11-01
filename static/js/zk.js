/*
 * Autenticación Zero Knowledge en el navegador.
 * - Registro: H = SHA256(salt + password); se envía solo H.
 * - Login:    se pide {salt, nonce} al servidor y se envía R = SHA256(SHA256(salt + password) + nonce).
 * Los inputs de contraseña NO tienen atributo `name`, así que el navegador nunca los envía.
 */
(function () {
  'use strict';

  // Respaldo en JS puro para contextos no seguros (http por IP de red), donde crypto.subtle no existe.
  function sha256Puro(texto) {
    const K = [
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
      0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
      0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
      0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
      0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
      0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
    const H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    const bytes = Array.from(new TextEncoder().encode(texto));
    const largoBits = bytes.length * 8;
    bytes.push(0x80);
    while (bytes.length % 64 !== 56) bytes.push(0);
    for (let i = 7; i >= 0; i--) bytes.push(i >= 4 ? 0 : (largoBits >>> (i * 8)) & 0xff);
    const rotr = (x, n) => (x >>> n) | (x << (32 - n));
    const W = new Array(64);
    for (let off = 0; off < bytes.length; off += 64) {
      for (let t = 0; t < 16; t++) {
        W[t] = (bytes[off + 4 * t] << 24) | (bytes[off + 4 * t + 1] << 16) | (bytes[off + 4 * t + 2] << 8) | bytes[off + 4 * t + 3];
      }
      for (let t = 16; t < 64; t++) {
        const s0 = rotr(W[t - 15], 7) ^ rotr(W[t - 15], 18) ^ (W[t - 15] >>> 3);
        const s1 = rotr(W[t - 2], 17) ^ rotr(W[t - 2], 19) ^ (W[t - 2] >>> 10);
        W[t] = (W[t - 16] + s0 + W[t - 7] + s1) | 0;
      }
      let [a, b, c, d, e, f, g, h] = H;
      for (let t = 0; t < 64; t++) {
        const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        const t1 = (h + S1 + ((e & f) ^ (~e & g)) + K[t] + W[t]) | 0;
        const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        const t2 = (S0 + ((a & b) ^ (a & c) ^ (b & c))) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      [a, b, c, d, e, f, g, h].forEach((v, i) => { H[i] = (H[i] + v) | 0; });
    }
    return H.map(v => (v >>> 0).toString(16).padStart(8, '0')).join('');
  }

  async function sha256Hex(texto) {
    if (window.crypto && window.crypto.subtle) {
      const buffer = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(texto));
      return Array.from(new Uint8Array(buffer)).map(b => b.toString(16).padStart(2, '0')).join('');
    }
    return sha256Puro(texto);
  }
  window.sha256Hex = sha256Hex;

  function mostrarError(form, mensaje) {
    const caja = form.querySelector('.zk-error');
    if (caja) { caja.textContent = mensaje; caja.classList.remove('d-none'); } else { alert(mensaje); }
  }

  document.addEventListener('DOMContentLoaded', function () {
    const login = document.getElementById('form-login');
    if (login) {
      login.addEventListener('submit', async function (ev) {
        ev.preventDefault();
        const username = login.querySelector('[name=username]').value.trim();
        const campoPassword = document.getElementById('password');
        const csrf = login.querySelector('[name=csrfmiddlewaretoken]').value;
        try {
          const resp = await fetch(login.dataset.desafio, {
            method: 'POST', headers: {'X-CSRFToken': csrf}, body: new URLSearchParams({username}),
          });
          const {salt, nonce} = await resp.json();
          const H = await sha256Hex(salt + campoPassword.value);
          login.querySelector('[name=respuesta]').value = await sha256Hex(H + nonce);
          campoPassword.value = '';
          login.submit();
        } catch (e) {
          mostrarError(login, 'No fue posible completar el desafío de autenticación.');
        }
      });
    }

    document.querySelectorAll('form[data-zk-salt]').forEach(function (form) {
      form.addEventListener('submit', async function (ev) {
        ev.preventDefault();
        const p1 = form.querySelector('#password');
        const p2 = form.querySelector('#password2');
        if (p1.value.length < 8) { mostrarError(form, 'La contraseña debe tener al menos 8 caracteres.'); return; }
        if (p1.value !== p2.value) { mostrarError(form, 'Las contraseñas no coinciden.'); return; }
        form.querySelector('[name=password_hash]').value = await sha256Hex(form.dataset.zkSalt + p1.value);
        p1.value = ''; p2.value = '';
        form.submit();
      });
    });
  });
})();
